"""Draw and pick UV correspondences without changing Max scene data."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


_COLORS = {'a': '#487734', 'b': '#ad571e'}
_LINK_COLORS = ('#7143a2', '#126e91', '#a83459', '#276c63',
                '#81571a', '#455db3', '#963882', '#43622c')
_HIT_RADIUS = 10


def _project(rect, geometry):
    points = [p for face in geometry for p in face]
    lo_x = min(p.real for p in points)
    hi_x = max(p.real for p in points)
    lo_y = min(p.imag for p in points)
    hi_y = max(p.imag for p in points)
    scale = min(max(1., rect.width()) / max(hi_x-lo_x, 1e-12),
                max(1., rect.height()) / max(hi_y-lo_y, 1e-12))
    center = complex(lo_x+(hi_x-lo_x)/2, lo_y+(hi_y-lo_y)/2)
    pixel = rect.center()
    return lambda p: QPointF(pixel.x()+(p-center).real*scale, pixel.y()-(p-center).imag*scale)


def _paths(faces, project):
    path = QPainterPath()
    for face in faces:
        if not face:
            continue
        path.moveTo(project(face[0]))
        for point in face[1:]:
            path.lineTo(project(point))
        path.closeSubpath()
    return path


def _pen(color, width, style=Qt.PenStyle.SolidLine):
    return QPen(QColor(color), width, style, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def _middle(a, b):
    return (a+b)/2


def _distance2(point, start, end):
    dx, dy = end.x()-start.x(), end.y()-start.y()
    px, py = point.x()-start.x(), point.y()-start.y()
    length = dx*dx+dy*dy
    t = max(0., min(1., (px*dx+py*dy)/length)) if length else 0.
    return (px-t*dx)**2+(py-t*dy)**2


class Preview(QWidget):
    edgePicked = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(435, 260)
        self.setMouseTracking(True)
        self.setAccessibleName('UV 边配对和重叠预览')
        self.setAccessibleDescription('点击 A 和 B 的外边界建立配对。编号相同的边由临时桥线连接。')
        self._editable = True
        self.clear_scene()

    def clear_scene(self):
        self._scene = None
        self._layout = None
        self._hover = None
        self._links = ()
        self._pending = None
        self._show_bridges = True
        self.unsetCursor()
        self.update()

    def set_editable(self, editable):
        self._editable = bool(editable)
        if not self._editable:
            self._hover = None
            self.unsetCursor()
        self.update()

    def set_scene(self, a_faces, b_faces, a_loop, b_loop, output, links,
                  pending=None, labels=(), show_bridges=True):
        self._scene = (a_faces, b_faces, a_loop, b_loop, output, labels)
        self._links = tuple(links)
        self._pending = pending
        self._show_bridges = show_bridges
        self._layout = None
        self.update()

    def resizeEvent(self, event):
        self._layout = None
        super().resizeEvent(event)

    def _prepare_layout(self):
        if self._layout is not None or self._scene is None:
            return
        a_faces, b_faces, a_loop, b_loop, output, labels = self._scene
        width = self.width()-14.
        height = self.height()-14.
        # Leave space between the source diagrams so endpoint bridges are easy to follow.
        panels = {
            'a': QRectF(7., 7., width*.291, height),
            'b': QRectF(7.+width*.375, 7., width*.291, height),
            'result': QRectF(7.+width*.697, 7., width*.303, height),
        }
        layouts = {}
        for side, faces, loop in (('a', a_faces, a_loop), ('b', b_faces, b_loop)):
            box = panels[side]
            project = _project(box.adjusted(17., 48., -17., -32.), faces)
            rim = [project(p) for p in loop]
            edges = list(zip(rim, rim[1:]+rim[:1]))
            hole_labels = [(project(p), color, name) for p,color,name in labels
                           if name.lower().startswith(side)]
            layouts[side] = (box, _paths(faces, project), edges, hole_labels)
        box = panels['result']
        project = _project(box.adjusted(15., 48., -15., -30.),
                           [*a_faces, *output] if output else a_faces)
        layouts['result'] = (box, _paths(a_faces, project),
                             _paths(output, project) if output else None)
        self._layout = layouts

    def edge_points(self, side, index):
        """Return the screen-space endpoints of an outer boundary edge."""
        self._prepare_layout()
        if self._layout is None or side not in _COLORS:
            return None
        edges = self._layout[side][2]
        return edges[index] if 0 <= index < len(edges) else None

    def _pairs(self):
        for index, pair in enumerate(self._links, 1):
            a, b, *direction = pair
            edge_a, edge_b = self.edge_points('a', a), self.edge_points('b', b)
            if edge_a is None or edge_b is None:
                continue
            mapped_b = edge_b[::-1] if direction and direction[0] == -1 else edge_b
            yield index, _LINK_COLORS[(index-1)%len(_LINK_COLORS)], edge_a, mapped_b

    def bridge_segments(self):
        """Return the endpoint links currently displayed by the preview."""
        if not self._show_bridges:
            return []
        return [(a[0], b[0]) if endpoint == 0 else (a[1], b[1])
                for _, _, a, b in self._pairs() for endpoint in (0,1)]

    def _hit(self, point):
        self._prepare_layout()
        if not self._editable or self._layout is None:
            return None
        for side in _COLORS:
            box, _, edges, _ = self._layout[side]
            if box.contains(point) and edges:
                distance, index = min((_distance2(point, a, b), i)
                                      for i,(a,b) in enumerate(edges))
                if distance <= _HIT_RADIUS**2:
                    return side, index
        return None

    def mouseMoveEvent(self, event):
        hovered = self._hit(event.position())
        if hovered != self._hover:
            self._hover = hovered
            if hovered:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        picked = self._hit(event.position()) if event.button() == Qt.MouseButton.LeftButton else None
        if picked:
            self.edgePicked.emit(*picked)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#eff3ee'))
        self._prepare_layout()
        if self._layout is None:
            painter.setPen(QColor('#506452'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             '从两个 UV 块各选任意点、边或面，再读取选区')
            return
        for side, title in (('a','A  固定块'), ('b','B  移动块'), ('result','重叠预览')):
            box = self._layout[side][0]
            color = _COLORS.get(side, '#365347')
            painter.setPen(_pen('#d5e1d2', 1.))
            painter.setBrush(QColor('#fcfdfa'))
            painter.drawRoundedRect(box, 8., 8.)
            painter.setPen(QColor(color))
            font = painter.font()
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(box.adjusted(12., 4., -8., 0.).topLeft()+QPointF(0., 17.), title)
            font.setBold(False)
            painter.setFont(font)
        self._draw_source(painter, 'a')
        self._draw_source(painter, 'b')
        self._draw_result(painter)
        self._draw_pairs(painter)
        self._draw_pick(painter, self._hover, False)
        self._draw_pick(painter, self._pending, True)

    def _draw_source(self, painter, side):
        box, mesh, edges, labels = self._layout[side]
        color = _COLORS[side]
        faint = QColor(color)
        faint.setAlpha(120)
        painter.setPen(_pen(faint, 1.))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(mesh)
        painter.setPen(_pen(color, 2.2))
        for a,b in edges:
            painter.drawLine(a,b)
        for point, label_color, label in labels:
            self._chip(painter, point, label, label_color, [])

    def _draw_result(self, painter):
        box, fixed, moved = self._layout['result']
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(_COLORS['a'], 1.55))
        painter.drawPath(fixed)
        if moved is not None:
            painter.setPen(_pen(_COLORS['b'], 1.45, Qt.PenStyle.DashLine))
            painter.drawPath(moved)
            painter.setPen(QColor('#506452'))
            painter.drawText(box.adjusted(9., 0., -9., -8.),
                             Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignBottom,
                             'A 实线    B 虚线')
        else:
            painter.setPen(QColor('#506452'))
            painter.drawText(box.adjusted(8., 0., -8., -8.),
                             Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignBottom,
                             '等待确定对应边')

    def _draw_pairs(self, painter):
        used = []
        for index, color, a, b in self._pairs():
            if self._show_bridges:
                strip = QPainterPath(a[0])
                for point in (a[1], b[1], b[0]):
                    strip.lineTo(point)
                strip.closeSubpath()
                fill = QColor(color)
                fill.setAlpha(27)
                painter.fillPath(strip, fill)
                painter.setPen(_pen('#fcfdfa', 4.))
                painter.drawLine(a[0], b[0])
                painter.drawLine(a[1], b[1])
                painter.setPen(_pen(color, 1.75))
                painter.drawLine(a[0], b[0])
                painter.setPen(_pen(color, 1.6, Qt.PenStyle.DashLine))
                painter.drawLine(a[1], b[1])
            for edge in (a,b):
                painter.setPen(_pen('#fcfdfa', 6.))
                painter.drawLine(*edge)
                painter.setPen(_pen(color, 3.8))
                painter.drawLine(*edge)
                painter.setPen(_pen('#fcfdfa', 1.3))
                painter.setBrush(QColor(color))
                painter.drawEllipse(edge[0], 3.7, 3.7)
                end = edge[1]
                painter.drawRect(QRectF(end.x()-3.1, end.y()-3.1, 6.2, 6.2))
            midpoint_a, midpoint_b = _middle(*a), _middle(*b)
            if self._show_bridges:
                center_x = 7.+(self.width()-14.)*.333
                distance = midpoint_b.x()-midpoint_a.x()
                t = (center_x-midpoint_a.x())/distance if distance else .5
                center_y = midpoint_a.y()+(midpoint_b.y()-midpoint_a.y())*t
                self._chip(painter,QPointF(center_x,center_y),str(index),color,used)
            else:
                self._chip(painter,midpoint_a,str(index),color,used)
                self._chip(painter,midpoint_b,str(index),color,used)

    def _draw_pick(self, painter, picked, pending):
        if not picked or not self._editable:
            return
        edge = self.edge_points(*picked)
        if edge is None:
            return
        side,index = picked
        color = '#214e79' if pending else _COLORS[side]
        painter.setPen(_pen('#ffffff', 7.))
        painter.drawLine(*edge)
        painter.setPen(_pen(color, 4., Qt.PenStyle.DashLine if pending else Qt.PenStyle.SolidLine))
        painter.drawLine(*edge)
        text = f'{side.upper()} 边 {index+1}' + (' · 待配对' if pending else '')
        mid = _middle(*edge)
        self._chip(painter, QPointF(mid.x(), mid.y()-18.), text, color, [])

    def _chip(self, painter, point, text, color, occupied):
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(text)+10.
        height = metrics.height()+4.
        x = min(max(width/2+2.,point.x()),self.width()-width/2-2.)
        y = min(max(40.+height/2,point.y()),self.height()-height/2-7.)
        box = QRectF(x-width/2,y-height/2,width,height)
        offsets = (0., -1., 1., -2., 2., -3., 3.)
        for offset in offsets:
            candidate = box.translated(0.,offset*(height+3.))
            if candidate.top() >= 34. and candidate.bottom() <= self.height()-5. and not any(
                    candidate.intersects(other) for other in occupied):
                box = candidate
                break
        occupied.append(box)
        painter.setPen(_pen(color, 1.))
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(box, 4., 4.)
        painter.setPen(QColor(color))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)
