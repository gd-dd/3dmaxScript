"""Host acceptance for per-rig display scale and world-space child Bone tools.

Only run through run_rig_size_batch.py. Creates disposable scenes and never
shows a tool window. Tests host results, not mouse interaction or visual feel.
"""
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

SOURCE_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get('LX_RIG_RUNTIME_ROOT',str(SOURCE_ROOT))).resolve()
if not ROOT.is_relative_to(SOURCE_ROOT.parent):raise RuntimeError('Runtime must stay in E project isolation')
OUT = SOURCE_ROOT.parent / 'acceptance/rigskin-size-2026-11-11'
if os.environ.get('LX_RIG_SIZE_BATCH') != '1':
    raise RuntimeError('Use run_rig_size_batch.py; never run in a user Max scene')
RUN = Path(os.environ['LX_RIG_SIZE_RUN']).resolve()
if not RUN.is_relative_to((OUT / 'runs').resolve()) or not RUN.is_dir():
    raise RuntimeError('Expected a fresh E-drive batch output directory')
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from pymxs import runtime as rt
import pymxs
from rig import max_host as H, workflow_host as F

report = dict(pid=os.getpid(), script=str(Path(__file__).resolve()), output=str(RUN),
              runtimeRoot=str(ROOT),hostModule=str(Path(H.__file__).resolve()),
              scope='Dedicated hidden Max synthetic scenes; no user scene or visible UI acceptance', checks=[])
# 3dsmaxbatch wraps the Python entry evaluation in one startup hold. Close only
# that disposable entry hold, then balance it at exit. Production dispatch keeps
# its normal active-transaction guard and each command owns its real undo step.
startup_holds=0
while rt.theHold.Holding() and startup_holds<8:
    rt.theHold.Accept('Isolated batch entry');startup_holds+=1
assert not rt.theHold.Holding()
report['batchStartupHolds']=startup_holds


def write_report():
    (RUN / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')


def close(a, b, tolerance=2e-4):
    assert math.isclose(float(a), float(b), rel_tol=tolerance, abs_tol=tolerance * max(abs(float(b)), .001)), (a, b)


def vector(value):
    return tuple(float(v) for v in H.vec(value))


def near(a, b, tolerance=2e-4):
    a, b = tuple(a), tuple(b)
    assert math.dist(a, b) <= tolerance, (a, b, math.dist(a, b), tolerance)


def matrix(node):
    tm = node.transform
    return [vector(row) for row in (tm.row1, tm.row2, tm.row3, tm.row4)]


def unchanged(before, nodes, tolerance=2e-4):
    for node in nodes:
        for old, new in zip(before[H.handle(node)], matrix(node)):
            near(old, new, tolerance)


def node_ids():
    return {H.handle(node) for node in rt.objects}


def selection():
    return [H.handle(node) for node in rt.selection]


def call(action, **params):
    report['activeAction'] = action
    write_report()
    return H.dispatch(dict(action=action, params=params, scene=str(rt.LXRigSceneToken)))


def reset():
    rt.resetMaxFile(rt.Name('noPrompt'))
    rt.fileIn(str(ROOT / 'bridge/rig_context.ms'))


def reject(action, **params):
    before = node_ids()
    selected = selection()
    try:
        call(action, **params)
    except ValueError:
        pass
    else:
        raise AssertionError(action + ' accepted invalid input')
    assert node_ids() == before, 'Rejected command left scene objects: ' + action
    assert selection() == selected, 'Rejected command changed selection: ' + action


def make_bone(start, end, parent=None, name='ExternalBone'):
    result = H.create_bone(dict(start=start, end=end, name=name))
    bone = H.node(result['node'])
    F.free_bone(bone)
    if parent is not None:
        saved = rt.copy(bone.transform)
        bone.parent = parent
        bone.transform = saved
    return bone


def ik_size(goal, height, multiplier=1):
    for field, ratio in [('goalSize', .02), ('effectorSize', .015), ('vhSize', .015), ('vhLength', .1)]:
        close(rt.getProperty(goal.controller, rt.Name(field)), height * ratio * multiplier)


def display_size(control, height, multiplier=1):
    ratio = .05 if F.prop(control, 'LXRole') == 'Root' else .03
    expected = height * ratio * multiplier
    if H.cls(control) == 'Circle':
        close(control.radius, expected)
    elif H.cls(control) == 'Rectangle':
        close(control.width, expected * 2)
        close(control.length, expected * 2)
    elif H.cls(control) == 'Point':
        close(control.size, expected)
    else:
        raise AssertionError('Unexpected generated controller ' + H.cls(control))


def generated_scales():
    reset()
    rigs = []
    for index, height in enumerate((1.7, 170, 17000)):
        made = call('humanoid.create', height=height, prefix='Size' + str(index), fingers=1, toes=1,
                    origin=[index * height * 2, 0, 0])
        bones = [H.node(ref) for ref in made['nodes']]
        actual = F.scale_context()[made['nodes'][0]]['height']
        close(actual / height, .992, tolerance=.001)
        rigs.append(dict(height=height, actual=actual, made=made, bones=bones))
    rt.Box(name='UnrelatedFarBox', pos=rt.Point3(1e7, -1e7, 1e7), width=1e6, length=1e6, height=1e6)
    rt.Point(name='UnrelatedFarPoint', pos=rt.Point3(-1e7, 1e7, -1e7), size=1e6)
    sizes = F.scale_context()
    roots = []
    for index, rig in enumerate(rigs):
        made = rig['made']
        close(sizes[made['nodes'][0]]['height'], rig['actual'])
        done = call('rig.finalize', bones=made['nodes'], displayScale=1.25)
        goals = [H.node(ref) for ref in done['goals']]
        assert len(goals) == 4
        for goal in goals:
            ik_size(goal, rig['actual'], 1.25)
        created = call('controls.create', nodes=[] if index==0 else done['goals'], shape=('circle', 'rectangle', 'point')[index], displayScale=1.5)
        assert len(created['roots']) == 1 and len(created['controls']) == 4
        root = H.node(created['root'])
        roots.append(H.handle(root))
        near(vector(root.pos), (0, 0, 0))
        for ref in [created['root'], *created['controls']]:
            display_size(H.node(ref), rig['actual'], 1.5)
        rig.update(goals=goals, created=created)
    assert len(set(roots)) == 3, 'Different skeletons shared a Root'
    for rig in rigs:
        center = H.node(rig['made']['center'])
        assert H.handle(center.parent) == rig['created']['root'], 'BodyCenter attached to another skeleton Root'
    all_bones = [bone for rig in rigs for bone in rig['bones']]
    before = {H.handle(bone): matrix(bone) for bone in all_bones}
    call('controls.resize', nodes=[H.handle(rigs[0]['goals'][0])], displayScale=2, ikScale=.75)
    unchanged(before, all_bones, tolerance=.05)
    for index, rig in enumerate(rigs):
        for goal in rig['goals']:
            ik_size(goal, rig['actual'], .75 if index == 0 else 1.25)
        for ref in [rig['created']['root'], *rig['created']['controls']]:
            display_size(H.node(ref), rig['actual'], 2 if index == 0 else 1.5)
    return dict(heights=[r['height'] for r in rigs], actualHeights=[r['actual'] for r in rigs],
                independentRoots=roots, farObjectsIgnored=True, targetedResize=True)


def external_ik():
    reset()
    a = make_bone((0, 0, 0), (0, 0, 40), name='ImportedA')
    b = make_bone((0, 0, 40), (10, 0, 70), a, 'ImportedB')
    c = make_bone((10, 0, 70), (20, 0, 75), b, 'ImportedC')
    assert not any(F.prop(n, 'LXRigId') or F.prop(n, 'LXWorkflow') for n in (a, b, c))
    goal = rt.IKSys.ikChain(a, c, 'IKHISolver')
    assert goal is not None
    goal.name = 'External_HI_IK'
    sizes = F.scale_context()
    actual = sizes[H.handle(a)]['height']
    assert actual > 40
    close(sizes[H.handle(goal)]['height'], actual)
    before = {H.handle(node): matrix(node) for node in (a, b, c)}
    made = call('controls.create', nodes=[H.handle(goal)], shape='circle', displayScale=1.2)
    for ref in [made['root'], *made['controls']]:
        display_size(H.node(ref), actual, 1.2)
    call('controls.resize', nodes=[H.handle(goal)], displayScale=.8, ikScale=.6)
    ik_size(goal, actual, .6)
    for ref in [made['root'], *made['controls']]:
        display_size(H.node(ref), actual, .8)
    unchanged(before, (a, b, c))
    return dict(actualHeight=actual, ordinaryUntaggedBones=True, externalIK=True)


def child_world_space():
    reset()
    ancestor = rt.Point(name='ScaledParent')
    parent = make_bone((3, 4, 8), (13, 4, 8), ancestor, 'RotatedParentBone')
    rt.rotate(parent, rt.EulerAngles(18, 31, 57))
    old_child = make_bone((18, 4, 8), (18, 11, 8), parent, 'ExistingDescendant')
    old_grand = make_bone((18, 11, 8), (21, 14, 9), old_child, 'ExistingGrandchild')
    rt.scale(ancestor, rt.Point3(2, .65, 1.4))
    rt.rotate(ancestor, rt.EulerAngles(9, 17, 23))
    before = {H.handle(n): matrix(n) for n in (parent, old_child, old_grand)}
    original_start = vector(F.endpoint(parent))
    axis = F.endpoint(parent) - parent.objectTransform.row4
    unit = vector(rt.normalize(axis))
    rt.select(parent)
    captured = call('bone.parent_capture')
    assert captured['node'] == H.handle(parent)
    assert selection() == [H.handle(parent)]
    expected_start = original_start
    result_ids = []
    current = parent
    for index in range(3):
        result = call('bone.child', parent=H.handle(current), extend=True, length=7.25, name='Extended')
        child = H.node(result['node'])
        result_ids.append(result['node'])
        assert child.parent == current
        near(vector(H.position(child)), expected_start, .001)
        endpoint = vector(F.endpoint(child))
        close(math.dist(vector(H.position(child)), endpoint), 7.25)
        expected_end = tuple(a + d * 7.25 for a, d in zip(expected_start, unit))
        near(endpoint, expected_end, .003)
        assert selection() == [result['node']], 'New child was not selected for continuation'
        unchanged(before, (parent, old_child, old_grand), .001)
        current = child
        expected_start = expected_end
    return dict(children=result_ids, direction=unit, eachWorldLength=7.25,
                rotatedBone=True, nonUniformAncestor=True, descendantsUnchanged=True)


def independent_length_and_rejections():
    reset()
    parent = make_bone((0, 0, 0), (0, 0, 20))
    start = (8, 9, 10)
    endpoints = []
    for distance in (.01, 1, 10000):
        result = call('bone.child', parent=H.handle(parent), start=start,
                      direction=(8, 9 + distance, 10), length=6.75)
        endpoint = vector(F.endpoint(H.node(result['node'])))
        near(endpoint, (8, 15.75, 10), .001)
        endpoints.append(endpoint)
    rt.select(parent)
    reject('bone.child', parent=H.handle(parent), start=start, direction=start, length=6.75)
    reject('bone.child', parent=H.handle(parent), start=start, direction=(9, 9, 10), length=0)
    added=call('bone.child',parent=H.handle(parent),extend=True,length=6.75)
    pymxs.run_undo()
    assert added['node'] not in node_ids(),'Undo did not remove the child from the scene'
    pymxs.run_redo()
    restored=H.node(added['node']);assert restored.parent==parent
    close(math.dist(vector(H.position(restored)),vector(F.endpoint(restored))),6.75)
    pymxs.run_undo()
    resumed=call('bone.child',parent=added['node'],fallbackParent=H.handle(parent),extend=True,length=6.75)
    assert H.node(resumed['node']).parent==parent
    return dict(directionDistances=[.01, 1, 10000], endpoints=endpoints, noResidualObjects=True,undoRedoAndResume=True)


def selection_state(obj):
    current = rt.modPanel.getCurrentObject()
    return dict(nodes=selection(), modifiers=[H.handle(m) for m in obj.modifiers],
                base=H.handle(obj.baseObject), subObject=int(rt.subObjectLevel),
                current=H.handle(current) if current is not None else None,
                transform=matrix(obj), offset=(vector(obj.objectOffsetPos), vector(obj.objectOffsetScale)))


def affine_point(point, transform):
    # Explicit scalar affine transform, independent of Point3 * Matrix3 overload.
    p = vector(point)
    rows = [vector(r) for r in (transform.row1, transform.row2, transform.row3, transform.row4)]
    return tuple(sum(p[j] * rows[j][axis] for j in range(3)) + rows[3][axis] for axis in range(3))


def vertex_capture(edit_poly):
    reset()
    obj = rt.Box(name='CaptureMesh', width=12, length=16, height=20)
    rt.convertToPoly(obj)
    obj.pos = rt.Point3(21, -13, 37)
    rt.rotate(obj, rt.EulerAngles(27, 18, 43))
    rt.scale(obj, rt.Point3(1.7, .6, 2.2))
    obj.objectOffsetPos = rt.Point3(4, -2, 3)
    obj.objectOffsetRot = rt.eulerToQuat(rt.EulerAngles(11, 23, 7))
    obj.objectOffsetScale = rt.Point3(.8, 1.3, 1.1)
    rt.select(obj)
    rt.execute('max modify mode')
    rt.polyop.setVertSelection(obj.baseObject, F.bit([2]))
    chosen = [1, 3, 6]
    if edit_poly:
        modifier = rt.Edit_Poly()
        rt.addModifier(obj, modifier)
        rt.modPanel.setCurrentObject(modifier)
        rt.subObjectLevel = 1
        evaluated=rt.snapshotAsMesh(obj);rt.delete(evaluated);rt.completeRedraw()
        modifier.SetPrimaryNode(obj)
        choose = rt.execute('fn LXRigSizeSelect m n bits = (m.SetEPolySelLevel #Vertex; bits.count = m.GetNumVertices node:n; m.SetSelection #vertex &bits node:n)')
        with pymxs.undo(True,'Fixture vertex selection'):
            selection_result=choose(modifier, obj, F.bit(chosen))
        rt.completeRedraw()
        assert F.ids(modifier.GetSelection(rt.Name('vertex'), node=obj)) == chosen,dict(result=str(selection_result),level=str(modifier.GetEPolySelLevel()),subObject=int(rt.subObjectLevel),selection=F.ids(modifier.GetSelection(rt.Name('vertex'), node=obj)),defaultSelection=F.ids(modifier.GetSelection(rt.Name('vertex'))),vertices=int(modifier.GetNumVertices(node=obj)),current=H.cls(rt.modPanel.getCurrentObject()))
        points = [modifier.GetVertex(i, node=obj) for i in chosen]
    else:
        rt.modPanel.setCurrentObject(obj.baseObject)
        rt.subObjectLevel = 1
        rt.polyop.setVertSelection(obj.baseObject, F.bit(chosen))
        points = [rt.polyop.getVert(obj.baseObject, i) for i in chosen]
    transformed = [affine_point(point, obj.objectTransform) for point in points]
    expected = tuple(sum(point[axis] for point in transformed) / len(points) for axis in range(3))
    before = selection_state(obj)
    found = call('point.capture', mode='vertex')
    assert found['count'] == 3 and found['node'] == H.handle(obj)
    near(found['position'], expected, .001)
    assert selection_state(obj) == before, 'Capture changed selection, stack, transform or active modifier'
    if edit_poly:
        assert F.ids(modifier.GetSelection(rt.Name('vertex'), node=obj)) == chosen
    else:
        assert F.ids(rt.polyop.getVertSelection(obj.baseObject)) == chosen
    pivot = call('point.capture', mode='pivot')
    near(pivot['position'], vector(H.position(obj)), .001)
    assert math.dist(pivot['position'], vector(obj.objectTransform.row4)) > .1, 'Fixture failed to distinguish pivot/object offset'
    assert selection_state(obj) == before
    if edit_poly:
        clear = rt.execute('fn LXRigSizeClear m n = (local empty=#{}; empty.count = m.GetNumVertices node:n; m.SetSelection #Vertex &empty node:n)')
        clear(modifier, obj)
    else:
        rt.polyop.setVertSelection(obj.baseObject, F.bit([]))
    reject('point.capture', mode='vertex')
    return dict(mode='current Edit Poly' if edit_poly else 'base Editable Poly', count=3,
                expected=expected, actual=found['position'], stackAndSelectionPreserved=True,
                rotationScaleObjectOffset=True, emptySelectionRejected=True)


def biped_rejections():
    reset()
    com = rt.biped.createNew(170, -90, rt.Point3(0, 0, 0), arms=True, fingers=1, fingerLinks=1, toes=1, toeLinks=1)
    parts = [n for n in rt.objects if H.is_biped(n) and H.node_category(n) == 'bones']
    assert parts
    chosen = parts[0]
    all_parts = [n for n in rt.objects if H.is_biped(n)]
    before = {H.handle(n): matrix(n) for n in all_parts}
    parents = {H.handle(n): H.handle(n.parent) if n.parent else None for n in all_parts}
    rt.select(chosen)
    reject('bone.parent_capture')
    reject('bone.child', parent=H.handle(chosen), extend=True, length=10)
    reject('controls.create', nodes=[H.handle(chosen)], shape='circle')
    reject('controls.create', nodes=[], shape='circle')
    reject('controls.resize', nodes=[H.handle(chosen)], displayScale=1)
    reject('point.capture', node=H.handle(chosen), mode='vertex')
    unchanged(before, all_parts)
    assert parents == {H.handle(n): H.handle(n.parent) if n.parent else None for n in all_parts}
    return dict(bipedParts=len(parts), controlsAndFreeBoneGuarded=True, noResidualObjects=True,
                bipedHierarchyAndPosePreserved=True)


def partial_tags_and_unrelated_degenerate():
    reset()
    center=F.mark(rt.Point(),'controls','BodyCenter')
    a=make_bone((0,0,0),(0,0,10),center)
    b=make_bone((0,0,10),(0,0,100),a)
    rt.setUserProp(a,'LXRigId','PartialRig')
    bad=make_bone((10000,0,0),(10010,0,0));bad.length=0
    sizes=F.scale_context([a,b]);close(sizes[H.handle(a)]['height'],100);close(sizes[H.handle(b)]['height'],100)
    made=call('controls.create',nodes=[H.handle(a)],shape='circle')
    assert len(made['roots'])==1
    call('controls.resize',nodes=made['controls'],displayScale=1.5)
    display_size(H.node(made['controls'][0]),100,1.5)
    call('rig.finalize',bones=[H.handle(a),H.handle(b)])
    return dict(partialTagsHeight=100,unrelatedZeroLengthIgnored=True,allHostActions=True)


def installed_entry():
    sys.path.insert(0,str(SOURCE_ROOT/'tests/host'))
    from rig_entry_check import check
    return check(ROOT)


for name, check in [('generated_sizes_and_independent_roots', generated_scales),
                    ('untagged_external_bone_ik', external_ik),
                    ('child_world_rotation_scale_and_chain', child_world_space),
                    ('independent_length_and_invalid_points', independent_length_and_rejections),
                    ('base_poly_vertex_capture', lambda: vertex_capture(False)),
                    ('current_edit_poly_vertex_capture', lambda: vertex_capture(True)),
                    ('biped_rejections', biped_rejections),
                    ('partial_tags_and_unrelated_degenerate',partial_tags_and_unrelated_degenerate),
                    ('max_entry_lifecycle',installed_entry)]:
    item = dict(name=name, ok=False)
    report['checks'].append(item)
    report['activeCase'] = name
    write_report()
    started = time.monotonic()
    try:
        item.update(check())
        item['ok'] = True
    except Exception:
        item['error'] = traceback.format_exc()
    item['seconds'] = round(time.monotonic() - started, 3)
    write_report()
report['ok'] = all(item['ok'] for item in report['checks'])
report['maxVersion'] = list(rt.maxVersion())[:3]
report.pop('activeAction', None)
report.pop('activeCase', None)
write_report()
for _ in range(startup_holds):rt.theHold.Begin()
print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
