"""Draw and pick UV correspondences without changing Max scene data."""
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


_COLORS = {'a': '#487734', 'b': '#ad571e'}
_LINK_COLORS = ('#7143a2', '#126e91', '#a83459', '#276c63',
                '#81571a', '#455db3', '#963882', '#43622c')
_HIT_RADIUS = 10
_DEFAULT_TITLES = ('A  固定块', 'B  移动块', '重叠预览')


def _project(rect, geometry):
    points = [p for face in geometry for p in face]
    if not points:
        return None
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
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._press = None
        self._drag_target = None
        self._drag_delta = QPointF()
        self.setAccessibleName('UV 边配对和重叠预览')
        self.setAccessibleDescription('点击外边界配对。拖动原始 A、原始 B 或重叠中的 B 查看，松手回到原位。')
        self._editable = True
        self.clear_scene()

    def clear_scene(self):
        self._cancel_drag()
        self._scene = None
        self._layout = None
        self._hover = None
        self._links = ()
        self._point_links = ()
        self._titles = _DEFAULT_TITLES
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
                  pending=None, labels=(), show_bridges=True, titles=None, point_links=()):
        self._cancel_drag()
        self._scene = (a_faces, b_faces, a_loop, b_loop, output, labels)
        self._links = tuple(links)
        self._point_links = tuple(point_links)
        self._titles = titles or _DEFAULT_TITLES
        self._pending = pending
        self._show_bridges = show_bridges
        self._layout = None
        self.update()

    def resizeEvent(self, event):
        self._cancel_drag()
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
        self._projects = {}
        for side, faces, loop in (('a', a_faces, a_loop), ('b', b_faces, b_loop)):
            box = panels[side]
            project = _project(box.adjusted(17., 48., -17., -32.), faces)
            self._projects[side] = project
            rim = [project(p) for p in loop] if project else []
            edges = list(zip(rim, rim[1:]+rim[:1]))
            hole_labels = [(project(p), color, name) for p,color,name in labels
                           if project and name.lower().startswith(side)]
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
        if not 0 <= index < len(edges):
            return None
        offset = self.drag_offset(side)
        start,end = edges[index]
        return start+offset,end+offset

    def drag_offset(self, side):
        """Return a copy of the temporary pixel translation for a visible block."""
        return QPointF(self._drag_delta) if self._drag_target == side else QPointF()

    def overlap_bounds(self, side):
        """Return displayed bounds for fixed A or moved B in the overlap preview."""
        self._prepare_layout()
        if self._layout is None or side not in ('a', 'b'):
            return None
        path = self._layout['result'][1 if side == 'a' else 2]
        if path is None or path.isEmpty():
            return None
        offset = self.drag_offset('result') if side == 'b' else QPointF()
        return path.boundingRect().translated(offset)

    def _paired_edges(self):
        for pair in self._links:
            a, b, *direction = pair
            edge_a, edge_b = self.edge_points('a', a), self.edge_points('b', b)
            if edge_a is not None and edge_b is not None:
                yield edge_a, edge_b[::-1] if direction and direction[0] == -1 else edge_b
        self._prepare_layout()
        if not self._point_links or self._layout is None:
            return
        project_a,project_b = self._projects['a'],self._projects['b']
        if not project_a or not project_b:
            return
        offset_a,offset_b = self.drag_offset('a'),self.drag_offset('b')
        for a,b in self._point_links:
            yield tuple(project_a(point)+offset_a for point in a), tuple(project_b(point)+offset_b for point in b)

    def _pairs(self):
        for index,(a,b) in enumerate(self._paired_edges(), 1):
            yield index, _LINK_COLORS[(index-1)%len(_LINK_COLORS)], a, b

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

    def _drag_hit(self, point, picked=None):
        self._prepare_layout()
        if self._layout is None:
            return None
        if picked:
            return picked[0]
        for side in ('a', 'b', 'result'):
            box, path, *_ = self._layout[side]
            if side == 'result':
                path = self._layout[side][2]
            if path is not None and not path.isEmpty() and box.contains(point) and path.boundingRect().adjusted(
                    -_HIT_RADIUS, -_HIT_RADIUS, _HIT_RADIUS, _HIT_RADIUS).contains(point):
                return side
        return None

    def _cancel_drag(self):
        if self._press is None:
            return
        self._press = None
        self._drag_target = None
        self._drag_delta = QPointF()
        self._hover = None
        self.unsetCursor()
        self.update()

    def _track_pointer(self, point):
        hovered = self._hit(point)
        if hovered:
            cursor = Qt.CursorShape.PointingHandCursor
        elif self._drag_hit(point):
            cursor = Qt.CursorShape.OpenHandCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        if self.cursor().shape() != cursor:
            self.setCursor(cursor)
        if hovered != self._hover:
            self._hover = hovered
            self.update()

    def mouseMoveEvent(self, event):
        if self._press is not None:
            start, side, _ = self._press
            offset = event.position()-start
            if self._drag_target or offset.manhattanLength() >= QApplication.startDragDistance():
                self._drag_target = side
                self._drag_delta = offset
                self._hover = None
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.update()
            event.accept()
            return
        self._track_pointer(event.position())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._press is None:
            self._hover = None
            self.unsetCursor()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            point = event.position()
            picked = self._hit(point)
            side = self._drag_hit(point, picked)
            if side:
                self.setFocus(Qt.FocusReason.MouseFocusReason)
                self._press = (point, side, picked)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._press is not None:
            start, _, picked = self._press
            stays_click = self._drag_target is None and (
                event.position()-start).manhattanLength() < QApplication.startDragDistance()
            self._cancel_drag()
            if stays_click and self._editable and picked:
                self.edgePicked.emit(*picked)
            self._track_pointer(event.position())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def event(self, event):
        if getattr(self,'_press',None) is not None:
            if event.type() == QEvent.Type.ShortcutOverride and event.key() == Qt.Key.Key_Escape:
                event.accept()
                return True
            if event.type() in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate, QEvent.Type.UngrabMouse):
                self._cancel_drag()
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._press is not None:
            self._cancel_drag()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._cancel_drag()
        super().focusOutEvent(event)

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
        for side,title in zip(('a','b','result'),self._titles):
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
        for side in ('a','b'):
            if self._drag_target != side:
                self._draw_source(painter, side)
        if self._drag_target in ('a','b'):
            self._draw_source(painter, self._drag_target)
        self._draw_result(painter)
        self._draw_pairs(painter)
        self._draw_pick(painter, self._hover, False)
        self._draw_pick(painter, self._pending, True)

    def _draw_source(self, painter, side):
        box, mesh, edges, labels = self._layout[side]
        color = _COLORS[side]
        if mesh.isEmpty():
            painter.setPen(QColor('#506452'))
            painter.drawText(box,Qt.AlignmentFlag.AlignCenter,'该侧无对应孔')
            return
        faint = QColor(color)
        faint.setAlpha(120)
        painter.setPen(_pen(faint, 1.))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        offset = self.drag_offset(side)
        painter.save()
        painter.translate(offset)
        painter.drawPath(mesh)
        painter.setPen(_pen(color, 2.2))
        for a,b in edges:
            painter.drawLine(a,b)
        painter.restore()
        for point, label_color, label in labels:
            self._chip(painter, point+offset, label, label_color, [])

    def _draw_result(self, painter):
        box, fixed, moved = self._layout['result']
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(_pen(_COLORS['a'], 1.55))
        painter.drawPath(fixed)
        if moved is not None:
            painter.save()
            painter.setClipRect(box.adjusted(2., 31., -2., -24.))
            painter.translate(self.drag_offset('result'))
            painter.setPen(_pen(_COLORS['b'], 1.45, Qt.PenStyle.DashLine))
            painter.drawPath(moved)
            painter.restore()
            painter.setPen(QColor('#506452'))
            painter.drawText(box.adjusted(9., 0., -9., -8.),
                             Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignBottom,
                             'A 实线    B 虚线')
        else:
            painter.setPen(QColor('#506452'))
            both_sides = self._projects['a'] is not None and self._projects['b'] is not None
            painter.drawText(box.adjusted(8., 0., -8., -8.),
                             Qt.AlignmentFlag.AlignHCenter|Qt.AlignmentFlag.AlignBottom,
                             '等待确定对应边' if both_sides else '未配对')

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
                t = max(0., min(1., (center_x-midpoint_a.x())/distance)) if distance else .5
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
