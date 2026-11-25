"""Alignment for two polygonal UV islands. Coordinates are complex U + iV."""
from collections import Counter, defaultdict
from bisect import bisect_right


def islands(faces, selected):
    owners = defaultdict(list)
    for index, face in faces.items():
        for vertex in face:
            owners[vertex].append(index)
    seen = set()
    groups = []
    for seed in sorted(selected):
        if seed in seen or seed not in faces:
            continue
        pending = [seed]
        seen.add(seed)
        used_vertices = set()
        group = []
        while pending:
            index = pending.pop()
            face = faces[index]
            group.append(face)
            for vertex in face:
                if vertex not in used_vertices:
                    used_vertices.add(vertex)
                    for neighbor in owners[vertex]:
                        if neighbor not in seen:
                            seen.add(neighbor)
                            pending.append(neighbor)
        groups.append(group)
    return groups


def topology(faces):
    counts = Counter()
    neighbors = defaultdict(set)
    for face in faces:
        for a, b in zip(face, face[1:] + face[:1]):
            if a == b:
                raise ValueError('UV 面包含重合索引。')
            counts[tuple(sorted((a, b)))] += 1
            neighbors[a].add(b)
            neighbors[b].add(a)
    rim = defaultdict(list)
    for (a, b), count in counts.items():
        if count > 2:
            raise ValueError('UV 边被三个或更多面共用。')
        if count == 1:
            rim[a].append(b)
            rim[b].append(a)
    if not rim or any(len(adjacent) != 2 for adjacent in rim.values()):
        raise ValueError('UV 块需要闭合且连续的边界。')
    loops = []
    pending = set(rim)
    for start in sorted(rim):
        if start not in pending:
            continue
        loop = [start]
        prior = None
        while True:
            current = loop[-1]
            next_vertex = min(p for p in rim[current] if p != prior)
            if next_vertex == start:
                break
            loop.append(next_vertex)
            prior = current
        pending.difference_update(loop)
        loops.append(loop)
    return loops, neighbors


def area(points):
    origin = points[0]
    return sum(((p-origin).conjugate()*(q-origin)).imag
               for p,q in zip(points, points[1:]+points[:1])) / 2


def ordered_loops(loops, positions):
    return sorted(loops, key=lambda loop: -abs(area([positions[i] for i in loop])))


def boundary_selection(groups, vertices, positions, edge_count=None):
    expected = set()
    for group in groups:
        loops, _ = topology(group)
        outer = ordered_loops(loops, positions)[0]
        if not set(outer) <= vertices:
            raise ValueError('外边界未选完整。请在每个块上选中整圈外边界。')
        expected.update(outer)
    if expected != vertices or edge_count is not None and edge_count != len(expected):
        raise ValueError('请只选两圈完整外边界。孔洞在预览中自动匹配，也可以手动指定。')
    return groups


def perimeter(points):
    lengths = [0.]
    for a, b in zip(points, points[1:] + points[:1]):
        distance = abs(a-b)
        if distance < 1e-10:
            raise ValueError('UV 边界有零长度边，请先整理重合点。')
        lengths.append(lengths[-1]+distance)
    return [distance/lengths[-1] for distance in lengths]


def sample(points, distances, t):
    t %= 1
    index = bisect_right(distances, t)-1
    weight = (t-distances[index])/(distances[index+1]-distances[index])
    return points[index]*(1-weight)+points[(index+1)%len(points)]*weight


def fit(source, target, mirror):
    if mirror:
        source = [p.conjugate() for p in source]
    a, b = sum(source)/len(source), sum(target)/len(target)
    norm = sum(abs(p-a)**2 for p in source)
    if norm < 1e-18:
        raise ValueError('UV 边界太小，无法对齐。')
    scale = sum((q-b)*(p-a).conjugate() for p,q in zip(source,target))/norm
    return lambda point: b + scale*((point.conjugate() if mirror else point)-a)


def corners(points):
    return [i for i,p in enumerate(points)
            if ((p-points[i-1])*(points[(i+1)%len(points)]-p).conjugate()).real
            < .94*abs(p-points[i-1])*abs(points[(i+1)%len(points)]-p)]


class Boundary:
    def __init__(self, positions, a, b, mirror=False, reference=None, extra_score=None):
        self.a, self.b = a, b
        self.target = [positions[i] for i in a]
        self.source = [positions[i] for i in b]
        self.equal = len(a) == len(b)
        self.mirror = mirror
        source_area, target_area = area(self.source), area(self.target)
        if min(abs(source_area),abs(target_area)) < 1e-16:
            raise ValueError('UV 边界面积为零或接近零，请先检查展开。')
        self.direction = -1 if (source_area*target_area<0) != mirror else 1
        self.arcs = perimeter(self.target)
        self.source_arcs = perimeter(self.source)
        self.target_corners = corners(self.target)
        self.source_corners = corners(self.source)
        paired_corners = 3 <= len(self.target_corners)==len(self.source_corners)
        if self.equal:
            chosen = list(range(0,len(self.b),max(1,len(self.b)//48)))
            probes = [self.source[i] for i in chosen]
            def candidates(start):
                return [self.target[(start+self.direction*i)%len(self.a)] for i in chosen]
            choices = range(len(self.a))
        elif paired_corners:
            chosen = range(0,len(self.source_corners),max(1,len(self.source_corners)//48))
            probes = [self.source[self.source_corners[i]] for i in chosen]
            def candidates(start):
                return [self.target[self.target_corners[(start+self.direction*i)%len(self.target_corners)]] for i in chosen]
            choices = range(len(self.target_corners))
        else:
            fractions = [i/32 for i in range(32)]
            probes = [sample(self.source,self.source_arcs,t) for t in fractions]
            def candidates(start):
                return [sample(self.target,self.arcs,self.arcs[start]+self.direction*t) for t in fractions]
            choices = self.target_corners or range(0,len(self.a),max(1,len(self.a)//64))
        def score(start):
            target = candidates(start)
            move = reference if reference is not None else fit(probes,target,self.mirror)
            error = sum(abs(move(p)-q)**2 for p,q in zip(probes,target))/len(probes)
            return error if extra_score is None else error+extra_score(move)
        self.corner_mode = not self.equal and paired_corners
        self.phases = len(self.target_corners) if self.corner_mode else len(self.a)
        self.start = min(choices,key=score)

    def mapping(self, phase):
        start = (self.start+phase)%self.phases
        if self.equal:
            rim = [self.target[(start+self.direction*i)%len(self.a)] for i in range(len(self.b))]
        elif self.corner_mode:
            anchors = self.source_corners+[self.source_corners[0]+len(self.b)]
            rim = [0j]*len(self.b)
            for i,(lo,hi) in enumerate(zip(anchors,anchors[1:])):
                left = self.target_corners[(start+self.direction*i)%self.phases]
                right = self.target_corners[(start+self.direction*(i+1))%self.phases]
                span = ((self.arcs[right]-self.arcs[left])*self.direction)%1
                arc = lambda j: self.source_arcs[j%len(self.b)]+j//len(self.b)
                for j in range(lo,hi):
                    t = (arc(j)-arc(lo))/(arc(hi)-arc(lo))
                    rim[j%len(self.b)] = sample(self.target,self.arcs,self.arcs[left]+self.direction*span*t)
        else:
            rim = [sample(self.target,self.arcs,self.arcs[start]+self.direction*t) for t in self.source_arcs[:-1]]
        linked = (dict(zip(self.b, (self.a[(start+self.direction*i)%len(self.a)]
                                   for i in range(len(self.b))))) if self.equal else {})
        return dict(zip(self.b, rim)), linked


def loop_center(points):
    total = 0j
    length = 0.
    for p,q in zip(points, points[1:]+points[:1]):
        span = abs(p-q)
        total += (p+q)/2*span
        length += span
    if length < 1e-10:
        raise ValueError('孔边界长度为零，请先检查展开。')
    return total/length


class Alignment:
    def __init__(self, positions, a, b, mirror=False):
        self.positions = positions
        a_loops, self.na = topology(a)
        b_loops, self.nb = topology(b)
        if (max(map(len,a_loops+b_loops)) > 4096 or max(len(self.na),len(self.nb)) > 20000
                or max(len(a_loops),len(b_loops)) > 65):
            raise ValueError('UV 块过大或孔洞超过 64 个，请拆分后对齐。')
        self.a, *self.a_holes = ordered_loops(a_loops, positions)
        self.b, *self.b_holes = ordered_loops(b_loops, positions)
        self.mirror = mirror
        self.a_centers = [loop_center([positions[i] for i in loop]) for loop in self.a_holes]
        self.b_centers = [loop_center([positions[i] for i in loop]) for loop in self.b_holes]
        self.boundary = Boundary(positions, self.a, self.b, mirror, extra_score=self.hole_score)
        self.phases = self.boundary.phases
        self.equal = self.boundary.equal
        self.reference = None
        self.hole_boundaries = {}

    def hole_score(self, move):
        if not self.a_centers or not self.b_centers:
            return 0.
        moved = [move(p) for p in self.b_centers]
        return .25*sum(min(abs(p-q)**2 for q in self.a_centers) for p in moved)/len(moved)

    def pairs(self, move, overrides):
        # Each B hole can be assigned to only one A hole.
        pairs = dict(overrides)
        occupied = {i for i in pairs.values() if i is not None}
        candidates = sorted((abs(p-move(q)), a, b)
                            for a,p in enumerate(self.a_centers) if a not in pairs
                            for b,q in enumerate(self.b_centers) if b not in occupied)
        for _,a,b in candidates:
            if a not in pairs and b not in occupied:
                pairs[a] = b
                occupied.add(b)
        return {a:b for a,b in pairs.items() if b is not None}

    def result(self, phase, overrides=None):
        outer = self.boundary
        boundary, linked = outer.mapping(phase)
        move = fit(outer.source,[boundary[i] for i in self.b],self.mirror)
        if self.reference != phase:
            self.reference = phase
            self.hole_boundaries.clear()
        self.matched = self.pairs(move, overrides or {})
        for a,b in self.matched.items():
            if (a,b) not in self.hole_boundaries:
                self.hole_boundaries[a,b] = Boundary(self.positions,self.a_holes[a],
                                                      self.b_holes[b],self.mirror,reference=move)
            rim, correspondence = self.hole_boundaries[a,b].mapping(0)
            boundary.update(rim)
            linked.update(correspondence)

        points = {i:move(self.positions[i]) for i in self.nb}
        interior = self.nb.keys()-boundary.keys()
        offsets = {i:boundary[i]-points[i] if i in boundary else 0j for i in self.nb}
        for _ in range(24):
            offsets.update({i:sum(offsets[j] for j in self.nb[i])/len(self.nb[i]) for i in interior})
        points.update({i:points[i]+offsets[i] for i in interior})
        points.update(boundary)
        if self.equal:
            fixed_rim = set(self.a).union(*self.a_holes)
            moving_rim = set(self.b).union(*self.b_holes)
            candidates = self.na.keys()-fixed_rim
            # Use boundary-anchored graph propagation for matching layouts.
            used = set(linked.values())
            pending = set(interior)-moving_rim
            for _ in range(64):
                if not pending:
                    break
                proposals = {}
                for vertex in sorted(pending):
                    anchors = [self.na[linked[j]] for j in self.nb[vertex] if j in linked]
                    if anchors:
                        matches = {j for j in set.intersection(*anchors) & candidates - used
                                   if len(self.na[j])==len(self.nb[vertex])}
                        if len(matches)==1:
                            proposals[vertex] = matches.pop()
                counts = Counter(proposals.values())
                accepted = {i:j for i,j in proposals.items() if counts[j]==1}
                if not accepted:
                    break
                linked.update(accepted)
                used.update(accepted.values())
                pending.difference_update(accepted)
            if len(linked)==len(self.nb)==len(self.na) and all({linked[j] for j in adj}==self.na[linked[i]] for i,adj in self.nb.items()):
                return {i:self.positions[j] for i,j in linked.items()}, '逐点重叠'
            for i in interior & linked.keys():
                points[i] = self.positions[linked[i]]
            if len(pending)*len(candidates)<=400000:
                limit = max(abs(p-outer.target[0]) for p in outer.target)*.025
                for vertex in sorted(pending):
                    near = [(abs(points[vertex]-self.positions[j]),j) for j in candidates if j not in used]
                    if near:
                        distance, match = min(near)
                        if distance<=limit:
                            points[vertex]=self.positions[match]
                            used.add(match)
        return points, '边界对齐 · 内部映射' if self.equal else ('转角对齐 · 内部映射' if outer.corner_mode else '按轮廓对齐 · 内部映射')
