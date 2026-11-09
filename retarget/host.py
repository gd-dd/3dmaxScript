"""All pymxs access is synchronous on the Max main thread.

No process discovery, IPC, scene loading or implicit fallback to another instance.
"""
import math
import threading
import uuid


class MaxHost:
    def __init__(self):
        self.check_thread()
        import pymxs
        self.mx = pymxs
        self.rt = pymxs.runtime
        self._nodes = {}
        self._biped_write_layers = {}
        import os
        self.instance_label = f'3ds Max {self.rt.maxVersion()[7]} · PID {os.getpid()}'

    @staticmethod
    def check_thread():
        if threading.current_thread() is not threading.main_thread():
            raise RuntimeError("Max 场景只能在宿主主线程访问")

    def remember(self, node):
        self.check_thread()
        key = str(int(self.rt.getHandleByAnim(node)))
        self._nodes[key] = node
        return key

    def node(self, key):
        self.check_thread()
        node = self._nodes.get(str(key))
        if node is None or not self.rt.isValidNode(node):
            raise ValueError("节点已失效，请重新读取骨架：" + str(key))
        if str(int(self.rt.getHandleByAnim(node))) != str(key):
            raise ValueError("节点身份改变，请重新读取")
        return node

    def valid(self, key):
        try:
            self.node(key)
            return True
        except ValueError:
            return False

    def selection_ids(self):
        self.check_thread()
        return [self.remember(n) for n in self.rt.selection]

    def current_frame(self):
        self.check_thread()
        return float(self.rt.sliderTime.frame)

    def frame_range(self):
        self.check_thread()
        return (int(self.rt.animationRange.start.frame), int(self.rt.animationRange.end.frame))

    def describe(self, ids, include_children=False):
        from .model import Node
        self.check_thread()
        ordered, seen = [], set()
        def visit(n):
            if str(self.rt.classOf(n.controller)).lower() == 'footsteps':
                return
            if str(n.name).lower().endswith('nub'):
                ancestor=n.parent
                while ancestor is not None:
                    if self.is_biped(ancestor):return
                    ancestor=ancestor.parent
            key = self.remember(n)
            if key in seen:
                return
            seen.add(key)
            ordered.append(n)
            if include_children:
                for child in n.children:
                    visit(child)
        for key in ids:
            visit(self.node(key))
        out = []
        for n in ordered:
            parts, ancestor = [], n
            while ancestor is not None:
                parts.append(str(ancestor.name))
                ancestor = ancestor.parent
            parent = self.remember(n.parent) if n.parent is not None and self.remember(n.parent) in seen else None
            controller = str(self.rt.classOf(n.controller))
            lower = (str(self.rt.classOf(n)) + ' ' + controller).lower()
            kind = 'biped' if 'bip' in lower else ('cat' if 'cat' in lower else 'bone')
            writable = self.controller_supported(n)
            out.append(Node(id=self.remember(n), name=str(n.name), parent=parent,
                            path='/'.join(reversed(parts)), kind=kind, writable=writable,
                            animated=self.has_keys_controller(n.controller)))
        return out

    def controller_supported(self, n):
        self.check_thread()
        rt = self.rt
        if self.is_biped(n):
            try:
                ctrl = self.biped_root(n).controller
                return not bool(n.isNodeFrozen) and not bool(n.layer.isFrozen) and not any(bool(getattr(ctrl,p)) for p in
                    ('figureMode','footstepMode','motionMode','mixerMode','moveAllMode','bufferMode'))
            except Exception:
                return False
        if str(rt.classOf(n.controller)).lower() != 'prs':
            return False
        # Deliberately fail closed for constraints, lists, scripts, rigs and scale animation.
        expected = {'position': {'position_xyz', 'bezier_position', 'linear_position', 'tcb_position'},
                    'rotation': {'euler_xyz', 'tcb_rotation', 'bezier_rotation', 'linear_rotation'},
                    'scale': {'bezier_scale', 'linear_scale', 'tcb_scale', 'scalexyz'}}
        try:
            for prop, supported in expected.items():
                c = rt.getPropertyController(n.controller, rt.Name(prop))
                if str(rt.classOf(c)).lower() not in supported:
                    return False
                if prop in ('position', 'rotation'):
                    for i in range(1, int(c.numSubs) + 1):
                        sub = rt.getSubAnim(c, i)
                        ctrl = sub.controller
                        if ctrl is not None and str(rt.classOf(ctrl)).lower() not in {
                            'bezier_float', 'linear_float', 'tcb_float'}:
                            return False
                if prop == 'scale' and self.has_keys_controller(c):
                    return False
            if bool(n.isNodeFrozen) or bool(n.layer.isFrozen):
                return False
            # Locked transform channels must be explicitly unlocked by the user.
            if str(rt.getTransformLockFlags(n)) != '#{}':
                return False
        except Exception:
            return False
        return True

    def is_biped(self,n):
        self.check_thread()
        return str(self.rt.classOf(n)).lower() == 'biped_object'

    def biped_root(self,n):
        while n.parent is not None and self.is_biped(n.parent): n=n.parent
        if str(self.rt.classOf(n.controller)).lower()!='vertical_horizontal_turn':
            raise ValueError('无法找到 Biped COM 控制器')
        return n

    def has_biped(self,ids):
        return any(self.is_biped(self.node(k)) for k in ids)

    def validate_separation(self,source_ids,target_ids):
        source_ids,target_ids=set(source_ids),set(target_ids)
        roots=[]
        for ids,opposite in ((source_ids,target_ids),(target_ids,source_ids)):
            bip=set()
            for key in ids:
                n=self.node(key)
                if self.is_biped(n):bip.add(self.remember(self.biped_root(n)))
                parent=n.parent
                while parent is not None:
                    if self.remember(parent) in opposite:
                        raise ValueError('源与目标存在父子依赖，不能作为独立双骨架')
                    parent=parent.parent
            roots.append(bip)
        if roots[0]&roots[1]:raise ValueError('两侧属于同一个 Biped，不能独立重定向')

    def has_keys_controller(self, c, seen=None):
        self.check_thread()
        rt = self.rt
        seen=set() if seen is None else seen
        identity=int(rt.getHandleByAnim(c))
        if identity in seen:return False
        seen.add(identity)
        try:
            if int(rt.numKeys(c)) > 0:
                return True
        except Exception:
            pass
        for i in range(1, int(c.numSubs) + 1):
            sub = rt.getSubAnim(c, i)
            if sub.controller is not None and self.has_keys_controller(sub.controller,seen):
                return True
        return False

    def has_animation(self, ids):
        return any(self.has_keys_controller(self.node(key).controller) for key in ids)

    @staticmethod
    def vector(v):
        return (float(v.x), float(v.y), float(v.z))

    def sample(self, ids, frames):
        from .math3d import Transform
        self.check_thread()
        rt, result = self.rt, {}
        for frame in frames:
            pose = {}
            with self.mx.attime(frame):
                for key in ids:
                    n = self.node(key)
                    m = n.transform
                    if n.parent is not None and str(int(rt.getHandleByAnim(n.parent))) in ids:
                        m = m * rt.inverse(n.parent.transform)
                    q = m.rotationPart
                    scale = self.vector(m.scalePart)
                    if any(x <= 0 for x in scale) or max(scale)-min(scale)>1e-4:
                        raise ValueError(str(n.name) + '：负缩放或非均匀缩放需先处理')
                    # Reject shear instead of silently dropping it in decomposition.
                    rows = [self.vector(m.row1), self.vector(m.row2), self.vector(m.row3)]
                    for i, j in ((0, 1), (0, 2), (1, 2)):
                        if abs(sum(a*b for a,b in zip(rows[i],rows[j]))) > 1e-4*max(scale)**2:
                            raise ValueError(str(n.name) + '：剪切变换暂不能求解')
                    if float(rt.dot(rt.cross(m.row1,m.row2),m.row3))<=0:
                        raise ValueError(str(n.name)+'：镜像或奇异变换需先处理')
                    pose[key] = Transform(position=self.vector(m.translationPart),
                                          rotation=(-float(q.x),-float(q.y),-float(q.z),float(q.w)), scale=scale)
            result[frame] = pose
        return result

    def snapshot_controllers(self, ids):
        self.check_thread()
        prs, bip, bone_flags = {}, {}, {}
        for key in ids:
            n=self.node(key)
            if self.is_biped(n):
                root=self.biped_root(n); root_id=self.remember(root)
                if root_id not in bip:
                    ctrl=root.controller
                    bip[root_id]={'controller':ctrl,'current':int(self.rt.biped.getCurrentLayer(ctrl)),
                                  'index':None,'name':'LX 重定向 '+uuid.uuid4().hex[:8],
                                  'active':{i:bool(self.rt.biped.getLayerActive(ctrl,i)) for i in
                                            range(1,int(self.rt.biped.numLayers(ctrl))+1)}}
            else:
                prs[key]=n.controller
                ancestor=n
                while ancestor is not None:
                    if bool(ancestor.boneEnable):
                        bone_flags[self.remember(ancestor)]=bool(ancestor.boneAutoAlign)
                    ancestor=ancestor.parent
        return {'prs':prs,'biped':bip,'ids':list(ids),'bone_flags':bone_flags}

    def install_copies(self, originals):
        self.check_thread()
        for key in originals['bone_flags']:self.node(key).boneAutoAlign=False
        for key, controller in originals['prs'].items():
            cloned=self.rt.copy(controller)
            self.rt.clearControllerNewFlag(cloned)
            self.node(key).controller = cloned
            self.rt.invalidateTreeTM(self.node(key))
        for root_id,state in originals['biped'].items():
            ctrl=state['controller']; index=int(self.rt.biped.numLayers(ctrl))+1
            self.rt.biped.createLayer(ctrl,index,state['name'])
            state['index']=index
            self._biped_write_layers[root_id]=(index,state['name'])
            self.rt.biped.setCurrentLayer(ctrl,index)
            for old,active in state['active'].items():self.rt.biped.setLayerActive(ctrl,old,active)

    def restore_controllers(self, originals):
        self.check_thread()
        missing, errors = [], []
        for key in originals['bone_flags']:
            if self.valid(key):self.node(key).boneAutoAlign=False
        for key, controller in originals['prs'].items():
            if self.valid(key):
                try:
                    self.rt.clearControllerNewFlag(controller)
                    self.node(key).controller = controller
                except Exception as exc:errors.append(str(exc))
            else:
                missing.append(key)
        for key, state in originals['biped'].items():
            if not self.valid(key):
                self._biped_write_layers.pop(key,None)
                missing.append(key);continue
            if state['index'] is not None:
                try:
                    ctrl=state['controller'];index=state['index']
                    if str(self.rt.biped.getLayerName(ctrl,index))!=state['name']:
                        raise RuntimeError('Biped 层在操作中改变，不能安全删除；请检查 '+state['name'])
                    self.rt.biped.deleteLayer(ctrl,index)
                    state['index']=None
                    self._biped_write_layers.pop(key,None)
                    self.rt.biped.setCurrentLayer(ctrl,state['current'])
                    for old,active in state['active'].items():self.rt.biped.setLayerActive(ctrl,old,active)
                except Exception as exc:errors.append(str(exc))
        for key,flag in originals['bone_flags'].items():
            if self.valid(key):
                try:self.node(key).boneAutoAlign=flag
                except Exception as exc:errors.append(str(exc))
        for key in originals['prs']:
            if self.valid(key):self.rt.invalidateTreeTM(self.node(key))
        if errors:raise RuntimeError('恢复未完全成功：'+'；'.join(errors))
        return missing

    def finish_transaction(self,state):
        self.check_thread()
        for key,flag in state['bone_flags'].items():self.node(key).boneAutoAlign=flag
        for root_id,item in state['biped'].items():
            # Selecting a lower Biped layer hides evaluation of higher layers.
            # A committed result must remain the current active output layer.
            self._require_biped_write_layer(self.node(root_id))
            self.rt.biped.setCurrentLayer(item['controller'],item['index'])
            for old,active in item['active'].items():self.rt.biped.setLayerActive(item['controller'],old,active)
            self.rt.biped.setLayerActive(item['controller'],item['index'],True)
            self._biped_write_layers.pop(root_id,None)

    def clear_range(self,state,ids,start,end,translation_ids):
        self.check_thread()
        def clear(c):
            try:
                count=int(self.rt.numKeys(c))
                for index in range(count,0,-1):
                    frame=float(self.rt.getKeyTime(c,index).frame)
                    if start<=frame<=end:self.rt.deleteKey(c,index)
            except RuntimeError:
                pass
            for index in range(1,int(c.numSubs)+1):
                sub=self.rt.getSubAnim(c,index)
                if sub.controller is not None:clear(sub.controller)
        for key in state['prs']:
            n=self.node(key)
            clear(self.rt.getPropertyController(n.controller,self.rt.Name('rotation')))
            if key in translation_ids:
                clear(self.rt.getPropertyController(n.controller,self.rt.Name('position')))

    def prepare_bounds(self,state,all_ids,start,end,translation_ids):
        self.check_thread()
        state['guards']=self.sample(all_ids,[start-1,end+1])
        state['included_ids']=all_ids
        state['translations']=translation_ids

    def bound_layers(self,state,ids,start,end):
        self.check_thread()
        for frame,locals_ in state['guards'].items():
            pose={k:locals_[k] for k in ids}
            self.write_pose(pose,frame,state['translations'],key=True,included_ids=state['included_ids'])
            self.verify_pose(pose,frame,state['included_ids'],state['translations'])

    def verify_pose(self,pose,frame,all_ids,translation_ids=()):
        from .math3d import q_angle
        actual=self.sample(all_ids,[frame])[frame]
        for key,t in pose.items():
            if q_angle(actual[key].rotation,t.rotation)>0.002:
                raise ValueError(str(self.node(key).name)+'：宿主旋转写入受限，已回滚本次操作；期望 '+str(t.rotation)+'，实际 '+str(actual[key].rotation))
            if key in translation_ids and max(abs(a-b) for a,b in zip(actual[key].position,t.position))>0.01:
                raise ValueError(self.node(key).name+'：宿主位置被约束或夹紧，已回滚本次操作')

    def write_pose(self, pose, frame, translation_ids=(), key=True, included_ids=None):
        """Write rotations, then reconcile a complete native leg's FK endpoint.

        Biped's spine balance changes body positions while rotations are set.
        Its retained foot position can then project a correctly requested knee.
        Only an affected, completely mapped leg in this transaction's new layer
        may be reconciled. Session still verifies every mapped rotation and
        rolls back any remaining native restriction.
        """
        self.check_thread()
        # Native Biped metadata queries can evaluate its current-time pose.
        # Keep the entire operation at the requested frame, including preview.
        with self.mx.attime(frame):
            self._write_pose_balanced(pose,frame,translation_ids,key,included_ids)

    def _write_pose_balanced(self,pose,frame,translation_ids,key,included_ids):
        feet=[]
        roots={}
        for identity in pose:
            n=self.node(identity)
            if self.is_biped(n):
                root=self.biped_root(n);root_id=self.remember(root)
                if root_id not in roots:
                    self._require_biped_write_layer(root)
                    roots[root_id]=root
                part=self.rt.biped.getIdLink(n)
                # The verified correction is for ordinary three-link human legs.
                if int(part.x) in (5,6) and int(self.biped_root(n).controller.legLinks)==3 and int(part.y)==3:
                    feet.append(identity)
        self._write_pose_once(pose,frame,translation_ids,key,included_ids)
        if not feet:return
        from .math3d import q_angle,Transform
        ids=list(included_ids) if included_ids is not None else list(pose)
        for _ in range(2):
            actual=self.sample(ids,[frame])[frame]
            affected=set()
            for identity,goal in pose.items():
                n=self.node(identity)
                if self.is_biped(n) and q_angle(actual[identity].rotation,goal.rotation)>.0001:
                    part=self.rt.biped.getIdLink(n)
                    if int(part.x) in (5,6):
                        affected.add((self.remember(self.biped_root(n)),int(part.x)))
            selected=[]
            for identity in feet:
                n=self.node(identity);root=self.biped_root(n)
                limb=int(self.rt.biped.getIdLink(n).x);root_id=self.remember(root)
                if (root_id,limb) not in affected:continue
                self._require_biped_write_layer(root)
                required=self._biped_leg_ids(n,limb)
                if not required.issubset(pose):
                    raise ValueError(str(n.name)+'：原生腿解算需完整映射同侧大腿、小腿、脚及脚趾；已回滚本次操作')
                selected.append(identity)
            if not selected:return
            # Preserve LATEST native positions, including automatic body balance.
            # Overlay rotations only; reference/source positions give a different
            # ankle target once the spine has moved the body relative to COM.
            full=dict(actual)
            for identity,goal in pose.items():
                current=actual[identity]
                full[identity]=Transform(current.position,goal.rotation,current.scale)
            positions=self._biped_fk_positions(full,ids,selected)
            with self.mx.attime(frame),self.mx.animate(key):
                for identity,position in positions.items():
                    self.rt.biped.setTransform(self.node(identity),self.rt.Name('pos'),self.rt.Point3(*position),bool(key))
            self._write_pose_once({identity:full[identity] for identity in pose},frame,(),key,ids)

    def _require_biped_write_layer(self,root):
        owned=self._biped_write_layers.get(self.remember(root))
        if owned is None or int(self.rt.biped.getCurrentLayer(root.controller))!=owned[0] or (
            str(self.rt.biped.getLayerName(root.controller,owned[0]))!=owned[1]):
            raise ValueError('Biped 写入仅允许使用本次新建的结果层；请勿在操作中切换或改名动画层')

    def _biped_leg_ids(self,foot,limb):
        """Include every editable native participant of the same shared limb."""
        root_id=self.remember(self.biped_root(foot))
        top=foot
        while top.parent is not None and self.is_biped(top.parent):
            if int(self.rt.biped.getIdLink(top.parent).x)!=limb:break
            top=top.parent
        required=set()
        def visit(node):
            if not self.is_biped(node) or str(node.name).lower().endswith('nub'):return
            if self.remember(self.biped_root(node))!=root_id:return
            required.add(self.remember(node))
            for child in node.children:visit(child)
        visit(top)
        return required

    def _biped_fk_positions(self,full,ids,feet):
        from .model import Node,world_transforms
        nodes={}
        for identity in ids:
            n=self.node(identity)
            parent=str(int(self.rt.getHandleByAnim(n.parent))) if n.parent is not None else None
            nodes[identity]=Node(identity,str(n.name),parent=parent if parent in full else None)
        worlds=world_transforms(nodes,full)
        return {identity:worlds[identity].position for identity in feet}

    def _write_pose_once(self, pose, frame, translation_ids=(), key=True, included_ids=None):
        """Write only rotation and explicitly enabled root translation; never scale."""
        self.check_thread()
        from .math3d import q_rotate
        rt = self.rt
        included_ids=set(pose) if included_ids is None else set(included_ids)
        pending = set(pose)
        with self.mx.attime(frame), self.mx.animate(key):
            while pending:
                ready = [k for k in pending if self.node(k).parent is None or
                         str(int(rt.getHandleByAnim(self.node(k).parent))) not in pending]
                if not ready:
                    raise ValueError('目标层级存在环')
                for k in ready:
                    n, t = self.node(k), pose[k]
                    local = rt.Matrix3(*[rt.Point3(*q_rotate(t.rotation,axis)) for axis in
                                          ((1,0,0),(0,1,0),(0,0,1))],rt.Point3(*t.position))
                    parent_included=n.parent is not None and str(int(rt.getHandleByAnim(n.parent))) in included_ids
                    world = local * n.parent.transform if parent_included else local
                    if self.is_biped(n):
                        rt.biped.setTransform(n,rt.Name('rotation'),world.rotationPart,bool(key))
                        if k in translation_ids:
                            rt.biped.setTransform(n,rt.Name('pos'),world.translationPart,bool(key))
                    else:
                        # Write the cloned LOCAL tracks directly. Node.rotation /
                        # position invoke Bone-specific editing/auto-align state
                        # beyond the PRS tracks and cannot be used as a transaction.
                        controller_local = local if parent_included or n.parent is None else world*rt.inverse(n.parent.transform)
                        rotation=rt.getPropertyController(n.controller,rt.Name('rotation'))
                        rotation.value=controller_local.rotationPart
                        if k in translation_ids:
                            position=rt.getPropertyController(n.controller,rt.Name('position'))
                            position.value=controller_local.translationPart
                        rt.invalidateTreeTM(n)
                    pending.remove(k)

    def visibility_state(self, key):
        n = self.node(key)
        return {'hidden':bool(n.isNodeHidden), 'layer_hidden':bool(n.layer.isHidden),
                'effective_hidden':bool(n.isHiddenInVpt)}

    def set_hidden(self, key, hidden):
        n=self.node(key)
        # Max 2026 can ignore setting the node bit TRUE under a hidden layer.
        # No visible change is possible there; preserve both flags untouched.
        if bool(n.layer.isHidden):return
        n.isNodeHidden = bool(hidden)

    def select_nodes(self, ids):
        self.check_thread()
        self.rt.select(self.rt.Array(*[self.node(k) for k in ids]))

    def redraw(self):
        self.check_thread()
        self.rt.redrawViews()
