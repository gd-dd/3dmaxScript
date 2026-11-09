"""Explicit session state; source is fully sampled before any target mutation."""
from copy import deepcopy
from dataclasses import replace, asdict
from . import model, solver, preset, matching


class Session:
    def __init__(self, host):
        self.host = host
        self.config = model.SessionConfig({}, {}, model.humanoid_chains(), {}, {})
        self._visibility = {}
        self._preview = None
        self._last_bake = None
        self.revision = 0
        self.rebind_issues = []
        self._loaded_preset = None
        self._bindings = {'source':{},'target':{}}
        self._preset_live = None
        self._preset_issues = []

    @property
    def source(self): return list(self.config.source.values())
    @property
    def target(self): return list(self.config.target.values())
    @property
    def chains(self): return self.config.chains

    @property
    def settings(self):
        data = asdict(self.config.settings)
        data['output_mode'] = data.pop('existing_animation')
        data['chain_overrides'] = {c.name:{'rotation_weight':c.rotation_weight,
            'translation_weight':c.translation_weight,'offset':list(c.offset),
            'mapping_mode':getattr(c,'mapping_mode','auto')} for c in self.chains}
        return data

    def set_settings(self, values):
        self.invalidate_preview()
        self._settings(values)

    def invalidate_preview(self):
        self.restore_preview()
        self.revision += 1

    def capture(self, side, include_children=True):
        if side not in ('source', 'target'): raise ValueError('源/目标无效')
        nodes = self.host.describe(self.host.selection_ids(), include_children)
        if not nodes: raise ValueError('请先在 Max 中选择骨架根或节点集合')
        other = getattr(self.config, 'target' if side == 'source' else 'source')
        if set(n.id for n in nodes) & set(other):
            raise ValueError('源和目标不能包含相同节点，请选择独立骨架')
        self.invalidate_preview()
        self.restore_visibility()
        setattr(self.config, side, {n.id: n for n in nodes})
        setattr(self.config, side + '_reference', {})
        for chain in self.chains: setattr(chain, side, [])
        self.rebind_issues = []
        self._loaded_preset = None
        self._bindings = {'source':{},'target':{}}
        self._preset_live = None
        self._preset_issues = []
        return nodes

    def assign(self, chain_id, side, ids):
        if side not in ('source', 'target'): raise ValueError('侧别无效')
        ids = list(dict.fromkeys(str(i) for i in ids))
        nodes = getattr(self.config, side)
        if any(i not in nodes for i in ids): raise ValueError('节点不在此侧骨架中')
        chain = self._chain(chain_id)
        if side == 'target':
            used = {i for c in self.chains if c is not chain and c.enabled for i in c.target}
            if used.intersection(ids): raise ValueError('同一目标节点不能分配给多条链')
        self.invalidate_preview()
        setattr(chain, side, ids)

    def _chain(self, key):
        return next(c for c in self.chains if c.name == key)

    def add_chain(self, label, kind='custom'):
        label = label.strip()
        if not label or any(c.name == label for c in self.chains):
            raise ValueError('链名不能为空或重复')
        self.invalidate_preview()
        chain = model.Chain(label, [], [], kind=kind)
        self.chains.append(chain)
        return chain

    def remove_chain(self, key):
        self.invalidate_preview()
        self.config.chains.remove(self._chain(key))

    def reference(self, side, frame):
        nodes = getattr(self.config, side)
        if not nodes: raise ValueError('请先读取该侧骨架')
        self.invalidate_preview()
        pose = self.host.sample(list(nodes), [frame])[frame]
        setattr(self.config, side + '_reference', pose)
        return len(pose)

    def suggestions(self):
        result, reserved_source, reserved_target = [], set(), set()
        # A count mismatch needs both COMPLETE semantic spans. Pairwise name
        # candidates cannot represent newly inserted target joints.
        for chain in self.chains:
            if not chain.enabled or chain.kind not in ('spine','head'):
                continue
            role = '脊柱' if chain.kind=='spine' else '颈与头'
            source = sorted([k for k,n in self.config.source.items() if matching.chain_role(n.name)==role],
                            key=lambda k:self._depth(k,self.config.source))
            target = sorted([k for k,n in self.config.target.items() if matching.chain_role(n.name)==role],
                            key=lambda k:self._depth(k,self.config.target))
            if min(len(source),len(target))<2 or len(source)==len(target):continue
            if reserved_source.intersection(source) or reserved_target.intersection(target):continue
            if any(self.config.source[b].parent!=a for a,b in zip(source,source[1:])):continue
            if any(self.config.target[b].parent!=a for a,b in zip(target,target[1:])):continue
            result.append(dict(chain_id=chain.name,source=source,target=target,mapping_mode='resample',
                confidence=.78,reason=f'{role}语义及连续层级匹配；完整链 {len(source)}→{len(target)}，请确认首尾锚点后按弧长分布运动'))
            reserved_source.update(source);reserved_target.update(target)
        candidates = matching.suggest(self.config.source, self.config.target)
        pairs, used_targets = [], set()
        for sid in self.config.source:
            if sid in reserved_source:continue
            choices = sorted([p for p in candidates if p.source_id==sid and p.target_id not in reserved_target], key=lambda p:-p.confidence)
            if not choices: continue
            if len(choices)>1 and abs(choices[0].confidence-choices[1].confidence)<0.05: continue
            p=choices[0]
            if p.target_id in used_targets: continue
            used_targets.add(p.target_id); pairs.append(p)
        # Suggest named human chains without guessing hierarchy from alphabetical order.
        for c in self.chains:
            if any(row['chain_id']==c.name for row in result):continue
            token = c.kind if c.kind not in ('custom','arm','leg') else c.name
            candidates = []
            for p in pairs:
                s = self.config.source[p.source_id]
                if matching.chain_role(s.name) == c.name:
                    candidates.append(p)
            if not candidates:
                continue
            candidates.sort(key=lambda p: self._depth(p.source_id, self.config.source))
            result.append(dict(chain_id=c.name, source=[p.source_id for p in candidates],
                               target=[p.target_id for p in candidates],
                               confidence=min(p.confidence for p in candidates),
                               reason='；'.join(dict.fromkeys(p.reason for p in candidates))))
        # Include explicit unclassified one-to-one candidates as new custom chains.
        used = {i for row in result for i in row['source']}
        for p in pairs:
            if p.source_id not in used:
                result.append(dict(chain_id='匹配：'+self.config.source[p.source_id].name,
                                   source=[p.source_id], target=[p.target_id],
                                   confidence=p.confidence, reason=p.reason))
        return result

    @staticmethod
    def _depth(key, nodes):
        seen = set()
        while key in nodes and key not in seen:
            seen.add(key); key = nodes[key].parent
        return len(seen)

    def apply_suggestions(self, rows):
        backup = deepcopy(self.config.chains)
        try:
            names=[row['chain_id'] for row in rows]
            if len(names)!=len(set(names)):raise ValueError('同一条链只能确认一组建议')
            targets=[i for row in rows for i in row['target']]
            if len(targets)!=len(set(targets)):raise ValueError('建议包含重复目标，请逐项确认')
            self.invalidate_preview()
            for chain in self.chains:
                if chain.name in names:chain.target=[]
            for row in rows:
                if not any(c.name == row['chain_id'] for c in self.chains):
                    self.add_chain(row['chain_id'])
                self.assign(row['chain_id'], 'source', row['source'])
                self.assign(row['chain_id'], 'target', row['target'])
                if 'mapping_mode' in row:self._chain(row['chain_id']).mapping_mode=row['mapping_mode']
        except Exception:
            self.config.chains = backup
            raise

    def preflight(self):
        live_issues = []
        for side in ('source', 'target'):
            nodes = getattr(self.config,side)
            valid_ids = []
            for key,n in nodes.items():
                if not self.host.valid(n.id):
                    live_issues.append(model.Issue('error','deleted',n.name+' 已删除，请重新读取',n.id))
                else:
                    valid_ids.append(key)
            try:
                live = {n.id:n for n in self.host.describe(valid_ids,include_children=False)} if valid_ids else {}
                for key,current in live.items():
                    old = nodes[key]
                    if current.parent != old.parent:
                        live_issues.append(model.Issue('error','topology_changed',
                            current.name+' 父子关系已改变，请重新读取并采集参考姿态',key))
                    nodes[key] = replace(old, name=current.name,path=current.path,
                        kind=current.kind,writable=current.writable,
                        constraints=current.constraints,animated=current.animated)
            except Exception as exc:
                live_issues.append(model.Issue('error','host_preflight',f'{side}实时控制器检查失败：{exc}'))
        issues = list(model.preflight(self.config)) + live_issues
        for pending in self.rebind_issues:
            issues.append(model.Issue('error','unbound_preset',
                f'{pending.name} 尚未确认预设重绑定：{pending.reason}',pending.preset_id))
        target_biped = any(n.kind.lower()=='biped' for n in self.config.target.values())
        mode = self.config.settings.existing_animation
        if target_biped and mode!='new_layer':
            issues.append(model.Issue('error','biped_output','Biped 目标请明确选择「Biped 新动画层」输出，基础轨保持不变'))
        if not target_biped and mode=='new_layer':
            issues.append(model.Issue('error','bone_output','新层输出当前仅用于 Biped；普通 Bone 请选择区间覆盖或拒绝已有动画'))
        if hasattr(self.host,'validate_separation'):
            try:
                self.host.validate_separation(list(self.config.source),list(self.config.target))
            except Exception as exc:
                issues.append(model.Issue('error','separation',str(exc)))
        return issues

    def _settings(self, values, start=None, end=None, step=None):
        values = dict(values or {})
        self.config.settings = replace(self.config.settings,
            **{k:v for k,v in values.items() if k in model.Settings.__dataclass_fields__})
        self.config.settings.existing_animation = values.get('output_mode', self.config.settings.existing_animation)
        if start is not None: self.config.settings.start = int(start)
        if end is not None: self.config.settings.end = int(end)
        if step is not None: self.config.settings.step = int(step)
        for c in self.chains:
            overrides = values.get('chain_overrides', {}).get(c.name, {})
            c.rotation_weight = float(overrides.get('rotation_weight', values.get('rotation_weight', c.rotation_weight)))
            c.translation_weight = float(overrides.get('translation_weight', values.get('translation_weight', c.translation_weight)))
            if 'offset' in overrides: c.offset=tuple(overrides['offset'])
            if 'mapping_mode' in overrides:c.mapping_mode=overrides['mapping_mode']

    def _prepare(self, frames, cancelled, progress=None):
        errors = [i.message for i in self.preflight() if i.severity == 'error']
        if errors: raise ValueError('\n'.join(errors))
        if len(frames)*(len(self.config.source)+len(self.config.target))>1000000:
            raise ValueError('本次采样超过一百万个节点姿态，请缩短区间或增大步长后分段烘焙')
        samples, target_samples = {}, {}
        for index, f in enumerate(frames):
            if cancelled(): raise solver.CancelledError('已取消，未修改目标')
            samples.update(self.host.sample(list(self.config.source), [f]))
            target_samples.update(self.host.sample(list(self.config.target), [f]))
            if progress: progress(index+1,len(frames)*3)
        return solver.solve(self.config, samples, cancelled=cancelled, target_samples=target_samples)

    def _translations(self):
        return {i for c in self.chains if c.enabled and (c.kind == 'root' or c.translation_weight > 0) for i in c.target}

    def preview(self, frame, settings_dict=None):
        self.restore_preview()
        self._settings(settings_dict)
        poses = self._prepare([frame], lambda:False)
        ids = list(poses[frame])
        state = self.host.snapshot_controllers(ids)
        try:
            self.host.install_copies(state)
            self.host.write_pose(poses[frame], frame, self._translations(), key=False,included_ids=list(self.config.target))
            if hasattr(self.host,'verify_pose'):self.host.verify_pose(poses[frame],frame,list(self.config.target),self._translations())
        except BaseException:
            self.host.restore_controllers(state)
            raise
        self._preview = state
        self.host.redraw()
        return {'frame':frame,'nodes':len(ids),'revision':self.revision}

    def restore_preview(self):
        if self._preview is not None:
            missing = self.host.restore_controllers(self._preview)
            self._preview = None
            self.host.redraw()
            return missing
        return []

    def bake(self, start, end, step, settings_dict=None, progress=None, cancelled=None):
        self.restore_preview()
        cancelled = cancelled or (lambda:False)
        progress = progress or (lambda *args:None)
        self._settings(settings_dict, start, end, step)
        frames = list(self.config.settings.frames())
        poses = self._prepare(frames, cancelled, progress)
        ids = list(poses[frames[0]])
        biped = getattr(self.host,'has_biped',lambda ids:False)(ids)
        mode = self.config.settings.existing_animation
        if biped and mode!='new_layer':
            raise ValueError('Biped 目标请明确选择「Biped 新动画层」输出，基础轨保持不变')
        if not biped and mode=='new_layer':
            raise ValueError('新层输出当前仅用于 Biped；普通 Bone 请选择区间覆盖或拒绝已有动画')
        if self.config.settings.existing_animation == 'reject_existing' and self.host.has_animation(ids):
            raise ValueError('目标已有动画。请明确选择区间覆盖，或另存场景后处理。')
        state = self.host.snapshot_controllers(ids)
        if hasattr(self.host,'prepare_bounds'):self.host.prepare_bounds(state,list(self.config.target),frames[0],frames[-1],self._translations())
        try:
            self.host.install_copies(state)
            if hasattr(self.host,'clear_range'):self.host.clear_range(state,ids,frames[0],frames[-1],self._translations())
            if hasattr(self.host,'bound_layers'):self.host.bound_layers(state,ids,frames[0],frames[-1])
            # Never let pymxs.undo swallow an error and then return success.
            for index, frame in enumerate(frames):
                if cancelled(): raise solver.CancelledError('已取消，目标已恢复')
                self.host.write_pose(poses[frame], frame, self._translations(), key=True,included_ids=list(self.config.target))
                if hasattr(self.host,'verify_pose'):self.host.verify_pose(poses[frame],frame,list(self.config.target),self._translations())
                progress(len(frames)+index+1,len(frames)*3)
            # Shared Biped keys can be evaluated again when a later frame is
            # added. Verify the finished interval, not only each partial write.
            for index,frame in enumerate(frames):
                if cancelled():raise solver.CancelledError('已取消，目标已恢复')
                if hasattr(self.host,'verify_pose'):self.host.verify_pose(poses[frame],frame,list(self.config.target),self._translations())
                progress(len(frames)*2+index+1,len(frames)*3)
            if cancelled(): raise solver.CancelledError('已取消，目标已恢复')
            if hasattr(self.host,'finish_transaction'):self.host.finish_transaction(state)
        except BaseException:
            self.host.restore_controllers(state)
            raise
        self._last_bake = state
        self.host.redraw()
        return {'start':frames[0],'end':frames[-1],'frames':len(frames),'nodes':len(ids),
                'warnings':[f'原区间外关键帧保留；在 {frames[0]-1} 与 {frames[-1]+1} 帧添加原姿态边界保护键，边界附近插值仍可能变化。']}

    def restore_last_bake(self):
        if self._last_bake is None: raise ValueError('本会话没有可恢复的烘焙')
        missing = self.host.restore_controllers(self._last_bake)
        self._last_bake = None
        self.host.redraw()
        return missing

    def visibility(self, action, chain_id=None):
        self.restore_preview()
        source, target = set(self.config.source), set(self.config.target)
        all_ids = source | target
        if action == 'restore': return self.restore_visibility()
        current = set()
        if chain_id is not None:
            c = self._chain(chain_id); current = set(c.source+c.target)
        visible = {'show_source':source,'show_target':target,'hide_source':set(),'hide_target':set(),'show_all':all_ids,
                   'only_source':source,'only_target':target,'only_chain':current}.get(action)
        if visible is None: raise ValueError('未知显隐操作')
        affected = all_ids if action.startswith('only_') else (source if action=='hide_source' else target if action=='hide_target' else visible)
        blocked = []
        # Read the whole affected set before the first mutation: Max may propagate
        # visibility changes through hierarchical/layer display dependencies.
        for key in affected:
            if self.host.valid(key) and key not in self._visibility:
                self._visibility[key] = self.host.visibility_state(key)
        for key in affected:
            if not self.host.valid(key): continue
            self.host.set_hidden(key, key not in visible)
            if key in visible and self.host.visibility_state(key)['effective_hidden']: blocked.append(key)
        self.host.redraw()
        return {'blocked':blocked,'message':'部分节点受层、类别或冻结隐藏影响；未修改这些全局设置' if blocked else '显隐已更新'}

    def restore_visibility(self):
        missing, failed = [], {}
        for key, state in sorted(self._visibility.items(),key=lambda item:item[1]['hidden']):
            if self.host.valid(key):
                self.host.set_hidden(key, state['hidden'])
                if self.host.visibility_state(key)['hidden']!=state['hidden']:failed[key]=state
            else: missing.append(key)
        self._visibility=failed
        self.host.redraw()
        if failed:raise RuntimeError('部分节点隐藏标记未恢复；若所在层在会话期间被隐藏，请手动显示相应层后再次恢复：'+', '.join(failed))
        return missing

    def save_preset(self, path):
        if self.rebind_issues:
            raise ValueError(f'还有 {len(self.rebind_issues)} 个预设节点待重绑定，请先确认后保存')
        preset.save(path, self.config)

    def load_preset(self, path):
        loaded = preset.load(path)
        live = {side:dict(getattr(self.config,side)) for side in ('source','target')}
        bound, issues = preset.rebind(loaded, live['source'], live['target'])
        bindings = {'source':{}, 'target':{}}
        unresolved = {(issue.side,issue.preset_id) for issue in issues}
        # Keep the exact same decisions as preset.rebind (including collision checks).
        for side in ('source','target'):
            for old,n in getattr(loaded,side).items():
                if (side,old) in unresolved:
                    continue
                matches=[i for i,x in live[side].items() if x.path and x.path==n.path]
                if len(matches)==1:bindings[side][old]=matches[0]
            setattr(bound,side,live[side])
            ref = getattr(bound,side+'_reference')
            setattr(bound,side+'_reference',{k:v for k,v in ref.items() if k in live[side]})
        self.invalidate_preview()
        self._loaded_preset = loaded
        self._bindings = bindings
        self._preset_live = live
        self._preset_issues = list(issues)
        self.config = bound
        self.rebind_issues = issues
        return {'unresolved':[vars(i) for i in issues], 'message':f'{len(issues)} 个节点待确认重绑定；确认后可复用预设参考姿态，拓扑变化时请重新采集'}

    def apply_bindings(self, source_bindings, target_bindings):
        if self._loaded_preset is None: raise ValueError('请先加载预设')
        bindings = deepcopy(self._bindings)
        bindings['source'].update(source_bindings);bindings['target'].update(target_bindings)
        for side in ('source','target'):
            if any(not self.host.valid(key) for key in bindings[side].values()):
                raise ValueError('重绑定节点已删除，请重新读取骨架并加载预设')
        config = preset.apply_bindings(self._loaded_preset,self._preset_live['source'],self._preset_live['target'],
                                        bindings['source'],bindings['target'])
        # Placeholders never become host handles. Their unresolved identity lives
        # in rebind_issues and blocks preflight until explicitly confirmed.
        for side in ('source','target'):
            live = self._preset_live[side]
            setattr(config,side,dict(live))
            ref = getattr(config,side+'_reference')
            setattr(config,side+'_reference',{k:v for k,v in ref.items() if k in live})
        unresolved=[issue for issue in self._preset_issues if issue.preset_id not in bindings[issue.side]]
        self.invalidate_preview()
        self._bindings=bindings
        self.config=config
        self.rebind_issues=unresolved
        return {'message':'绑定已更新；可复用预设参考姿态，拓扑变化时请重新采集后预检','unresolved':[vars(i) for i in unresolved]}

    def select_nodes(self, ids): self.host.select_nodes(ids)

    def close(self):
        try:
            self.restore_preview()
        finally:
            self.restore_visibility()
