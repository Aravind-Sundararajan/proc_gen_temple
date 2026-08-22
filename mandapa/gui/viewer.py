"""The OpenGL preview: the document's :class:`~mandapa.look.Look`, rendered.

The viewer consumes a look; it never owns one.  The key light is stated in world space
(azimuth, elevation) and turned into the camera's frame every time a frame is drawn, so
the sun stays on the temple while the author orbits — the way daylight behaves on a
building, and the opposite of the old "light over the camera's shoulder" which made every
face the same brightness from every angle.  The backdrop gradient is also the fill light:
the sky tone lights faces that look up, the horizon tone faces that look down, so shadows
cool towards the sky instead of going grey.

One mesh item per build group is what makes "hide the roof to look inside" a visibility
flag rather than a rebuild; the print-risk colours are applied per group from masks that
were classified on the *whole* model (a roof classified alone would take its own underside
for the build plate).

Drawn in a fixed-function-free way throughout — VBOs, attribute arrays, pyqtgraph's own
shaders — so it works on the same contexts pyqtgraph 0.14 does.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pyqtgraph.opengl as gl
from OpenGL import GL
from pyqtgraph.opengl import shaders
from pyqtgraph.opengl.GLGraphicsItem import GLGraphicsItem
from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QMatrix4x4, QOpenGLContext, QVector3D
from PySide6.QtOpenGL import QOpenGLBuffer

from ..look import Look
from ..meshlib import Solid

__all__ = [
    "BED_COLOUR",
    "EDGE_COLOUR",
    "GRID_COLOUR",
    "VIEWS",
    "Backdrop",
    "BedOutline",
    "GroupMesh",
    "Viewer",
]

#: The wireframe's ivory.  The theme's INK is this colour; change it here, not there.
EDGE_COLOUR = (0.97, 0.95, 0.91, 1.0)
#: Grid lines: a cool grey at low alpha, furniture rather than subject.
GRID_COLOUR = (0.62, 0.66, 0.74, 0.30)
#: The print bed's plate outline, a little firmer than the grid it sits on.
BED_COLOUR = (0.62, 0.66, 0.74, 0.75)

#: Named views as (elevation, azimuth), Blender's numbers: Front looks along +Y from the
#: steps' side (the sopana is built on -Y), Right stands at +X, Top looks down with the
#: front at the bottom of the screen.
VIEWS: dict[str, tuple[float, float]] = {
    "front": (0.0, -90.0),
    "back": (0.0, 90.0),
    "right": (0.0, 0.0),
    "left": (0.0, 180.0),
    "top": (90.0, -90.0),
    "bottom": (-90.0, -90.0),
}

#: How long a snap-to-view travels, in milliseconds.  A cut to Top is indistinguishable
#: from a cut to Bottom on arrival; the sweep says which way the subject turned.
GLIDE_MS = 240

#: One turntable step every tick, in degrees; ~30 s for a full turn at 30 Hz.
TURNTABLE_STEP = 0.4
TURNTABLE_MS = 33

# The look shader.  Uniforms are float arrays rather than vec3s because pyqtgraph's
# ShaderProgram uploads every uniform with glUniform1fv; a vec3 fed that way is an
# INVALID_OPERATION, a float[3] is exactly right.
_LOOK_SHADER = shaders.ShaderProgram(
    "mandapaLook",
    [
        shaders.VertexShader(
            """
            uniform mat4 u_mvp;
            uniform mat3 u_normal;
            attribute vec4 a_position;
            attribute vec3 a_normal;
            attribute vec4 a_color;
            varying vec4 v_color;
            varying vec3 v_normal;
            varying float v_up;
            void main() {
                v_normal = normalize(u_normal * a_normal);
                v_up = a_normal.z;
                v_color = a_color;
                gl_Position = u_mvp * a_position;
            }
            """
        ),
        shaders.FragmentShader(
            """
            #ifdef GL_ES
            precision mediump float;
            #endif
            uniform float u_light[3];
            uniform float u_levels[3];
            uniform float u_sky[3];
            uniform float u_horizon[3];
            varying vec4 v_color;
            varying vec3 v_normal;
            varying float v_up;
            void main() {
                vec3 n = normalize(v_normal);
                vec3 l = normalize(vec3(u_light[0], u_light[1], u_light[2]));
                vec3 sky = vec3(u_sky[0], u_sky[1], u_sky[2]);
                vec3 horizon = vec3(u_horizon[0], u_horizon[1], u_horizon[2]);
                // The backdrop doubles as the fill: its hues tint the shadows but its
                // level must not darken them, so both tones are lifted to a common
                // brightness before they are mixed by how much the face looks up.
                float level = max(max(max(sky.r, sky.g), sky.b), 0.02);
                vec3 fill = mix(horizon, sky, clamp(0.5 + 0.5 * v_up, 0.0, 1.0)) / level;
                float key = max(dot(n, l), 0.0) * u_levels[0];
                float rim = pow(1.0 - max(n.z, 0.0), 3.0) * u_levels[2];
                vec3 light = fill * u_levels[1] + vec3(key) + (sky / level) * rim;
                vec3 rgb = min(v_color.rgb * light, vec3(1.0));
                gl_FragColor = vec4(rgb, v_color.a);
            }
            """
        ),
    ],
)

_IDENTITY = np.eye(4, dtype=np.float32).flatten()


@dataclass
class GroupMesh:
    """One build group as the viewer draws it: the merged solid and its risk masks."""

    solid: Solid
    steep: np.ndarray | None = None
    flat: np.ndarray | None = None


def _es2_compat() -> bool:
    context = QOpenGLContext.currentContext()
    return bool(context is not None and context.hasExtension(b"GL_ARB_ES2_compatibility"))


class Backdrop(GLGraphicsItem):
    """The vertical gradient behind everything: horizon at the bottom, sky at the top.

    A clip-space quad drawn first with the depth test off and depth writes off, so it
    can neither hide geometry nor be hidden by it.  It borrows pyqtgraph's plain colour
    shader with an identity MVP — the cheapest correct way to paint a gradient on a
    context that may have no fixed-function pipeline.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setDepthValue(-1000)
        self.setGLOptions({GL.GL_DEPTH_TEST: False, GL.GL_BLEND: False, GL.GL_CULL_FACE: False})
        self._bottom = (0.0, 0.0, 0.0)
        self._top = (0.0, 0.0, 0.0)
        self._vbo_position = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._vbo_colour = QOpenGLBuffer(QOpenGLBuffer.Type.VertexBuffer)
        self._dirty = True

    def set_colours(self, bottom: tuple[float, ...], top: tuple[float, ...]) -> None:
        self._bottom = tuple(float(c) for c in bottom[:3])
        self._top = tuple(float(c) for c in top[:3])
        self._dirty = True
        self.update()

    def _upload(self) -> None:
        position = np.array(
            [[-1, -1, 0], [1, -1, 0], [-1, 1, 0], [1, 1, 0]], dtype=np.float32
        )
        colour = np.array(
            [[*self._bottom, 1.0], [*self._bottom, 1.0], [*self._top, 1.0], [*self._top, 1.0]],
            dtype=np.float32,
        )
        for vbo, data in ((self._vbo_position, position), (self._vbo_colour, colour)):
            if not vbo.isCreated():
                vbo.create()
            vbo.bind()
            if vbo.size() != data.nbytes:
                vbo.allocate(data, data.nbytes)
            else:
                vbo.write(0, data, data.nbytes)
            vbo.release()
        self._dirty = False

    def paint(self) -> None:
        self.setupGLState()
        GL.glDepthMask(GL.GL_FALSE)
        try:
            if self._dirty:
                self._upload()
            shader = shaders.getShaderProgram(None)
            program = shader.program(es2_compat=_es2_compat())
            enabled = []
            if (loc := GL.glGetAttribLocation(program, "a_position")) != -1:
                self._vbo_position.bind()
                GL.glVertexAttribPointer(loc, 3, GL.GL_FLOAT, False, 0, None)
                self._vbo_position.release()
                enabled.append(loc)
            if (loc := GL.glGetAttribLocation(program, "a_color")) != -1:
                self._vbo_colour.bind()
                GL.glVertexAttribPointer(loc, 4, GL.GL_FLOAT, False, 0, None)
                self._vbo_colour.release()
                enabled.append(loc)
            for loc in enabled:
                GL.glEnableVertexAttribArray(loc)
            with shader:
                GL.glUniformMatrix4fv(GL.glGetUniformLocation(program, "u_mvp"), 1, False, _IDENTITY)
                GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)
            for loc in enabled:
                GL.glDisableVertexAttribArray(loc)
        finally:
            GL.glDepthMask(GL.GL_TRUE)


class BedOutline(GLGraphicsItem):
    """The printer's plate, centred on the origin: a rectangle and four corner posts.

    Only the plate is drawn firmly.  The full volume as a wire box stood 250 mm of posts
    around a 66 mm temple and owned the frame; short ticks at the corners say "there is
    a height limit" without drawing it.
    """

    TICK_FRACTION = 0.08

    def __init__(self) -> None:
        super().__init__()
        self.lines = gl.GLLinePlotItem(parentItem=self, glOptions="translucent", mode="lines", antialias=True)
        self._size = (220.0, 220.0, 250.0)
        self._scale = 1.0
        self.set_size(self._size)

    def set_size(self, size: tuple[float, float, float], scale: float = 1.0) -> None:
        """``size`` is the bed in mm; ``scale`` the export scale the preview is not drawn at."""
        self._size = tuple(float(v) for v in size)
        self._scale = max(float(scale), 1e-6)
        x, y, z = (v / self._scale for v in self._size)
        hx, hy = x / 2.0, y / 2.0
        tick = z * self.TICK_FRACTION
        corners = [(-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy)]
        segments = []
        for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
            segments += [(ax, ay, 0.0), (bx, by, 0.0)]
        for cx, cy in corners:
            segments += [(cx, cy, 0.0), (cx, cy, tick)]
        pos = np.array(segments, dtype=np.float32)
        colour = np.tile(np.array(BED_COLOUR, dtype=np.float32), (len(pos), 1))
        colour[8:, 3] *= 0.5
        self.lines.setData(pos=pos, color=colour, width=1.0)
        self.update()

    @property
    def size(self) -> tuple[float, float, float]:
        return self._size


class Viewer(gl.GLViewWidget):
    """The preview widget.  Mouse orbits, pans and zooms as pyqtgraph does."""

    #: The turntable started or stopped, including by the user grabbing the view.
    turntable_changed = Signal(bool)

    def __init__(self, look: Look | None = None, parent=None):
        super().__init__(parent)
        self._look = look or Look()
        self._orthographic = False
        self._highlight = True
        self._wireframe = False
        self._groups: dict[str, GroupMesh] = {}
        self._items: dict[str, gl.GLMeshItem] = {}
        self._hidden: set[str] = set()

        self.backdrop = Backdrop()
        self.addItem(self.backdrop)
        self.grid = gl.GLGridItem(color=tuple(round(c * 255) for c in GRID_COLOUR))
        self.grid.setSpacing(10, 10)
        self.grid.setSize(200, 200)
        self.addItem(self.grid)
        self.bed = BedOutline()
        self.addItem(self.bed)

        self.setCameraPosition(distance=320, elevation=22, azimuth=-55)

        self._turntable = QTimer(self)
        self._turntable.setInterval(TURNTABLE_MS)
        self._turntable.timeout.connect(lambda: self.orbit(-TURNTABLE_STEP, 0.0))

        self._glide = QVariantAnimation(self)
        self._glide.setDuration(GLIDE_MS)
        self._glide.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._glide.valueChanged.connect(self._glide_step)
        self._glide_from: tuple[float, float] = (0.0, 0.0)
        self._glide_to: tuple[float, float] = (0.0, 0.0)

        # Reachable by Tab as well as by click: the single-key verbs (F, 1/3/7, Space)
        # live here, and a keyboard user needs a way in that is not the mouse.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.set_look(self._look)

    # ---- the look ---------------------------------------------------------------------
    @property
    def look(self) -> Look:
        return self._look

    def set_look(self, look: Look) -> None:
        self._look = look
        self.backdrop.set_colours(look.background_colour, look.background_top)
        self.setBackgroundColor(tuple(round(max(0.0, min(1.0, c)) * 255) for c in look.background_colour))
        self._recolour()
        self.update()

    def paint(self, *, region, viewport, useItemNames=False):
        """Upload the look before the items draw: the key light in the camera's frame."""
        look = self._look
        direction = self.viewMatrix().mapVector(QVector3D(*look.direction()))
        if direction.isNull():
            direction = QVector3D(0.0, 0.0, 1.0)
        direction.normalize()
        _LOOK_SHADER["u_light"] = [direction.x(), direction.y(), direction.z()]
        _LOOK_SHADER["u_levels"] = [look.light_strength, look.ambient_strength, look.rim_strength]
        _LOOK_SHADER["u_sky"] = list(look.background_top)
        _LOOK_SHADER["u_horizon"] = list(look.background_colour)
        super().paint(region=region, viewport=viewport, useItemNames=useItemNames)

    # ---- the model --------------------------------------------------------------------
    def set_build(self, groups: dict[str, GroupMesh]) -> None:
        """Replace the model with one mesh item per group; visibility flags survive."""
        for name in list(self._items):
            if name not in groups or len(groups[name].solid.faces) == 0:
                self.removeItem(self._items.pop(name))
        self._groups = {name: group for name, group in groups.items() if len(group.solid.faces)}
        for name, group in self._groups.items():
            data = gl.MeshData(
                vertexes=np.ascontiguousarray(group.solid.vertices, dtype=np.float32),
                faces=np.ascontiguousarray(group.solid.faces),
                faceColors=self._colours(group),
            )
            item = self._items.get(name)
            if item is None:
                item = gl.GLMeshItem(
                    meshdata=data,
                    smooth=False,
                    shader="mandapaLook",
                    drawEdges=self._wireframe,
                    edgeColor=EDGE_COLOUR,
                    glOptions=self._gl_options(),
                )
                item.setVisible(name not in self._hidden)
                self._items[name] = item
                self.addItem(item)
            else:
                item.setMeshData(meshdata=data)
        self._fit_grid()
        self.update()

    def group_names(self) -> list[str]:
        return list(self._groups)

    def set_group_visible(self, name: str, visible: bool) -> None:
        if visible:
            self._hidden.discard(name)
        else:
            self._hidden.add(name)
        if (item := self._items.get(name)) is not None:
            item.setVisible(visible)

    def is_group_visible(self, name: str) -> bool:
        return name not in self._hidden

    def bounds(self, visible_only: bool = True) -> tuple[np.ndarray, np.ndarray] | None:
        """Bounds of the drawn model, or None before the first build."""
        los, his = [], []
        for name, group in self._groups.items():
            if visible_only and name in self._hidden:
                continue
            lo, hi = group.solid.bounds
            los.append(lo)
            his.append(hi)
        if not los:
            return None
        return np.min(los, axis=0), np.max(his, axis=0)

    def _colours(self, group: GroupMesh) -> np.ndarray:
        look = self._look
        count = len(group.solid.faces)
        colours = np.tile(np.array([*look.surface_colour, 1.0], dtype=np.float32), (count, 1))
        if self._highlight:
            if group.flat is not None and len(group.flat) == count:
                colours[group.flat] = [*look.bridge_colour, 1.0]
            if group.steep is not None and len(group.steep) == count:
                colours[group.steep] = [*look.overhang_colour, 1.0]
        return colours

    def _recolour(self) -> None:
        for name, item in self._items.items():
            group = self._groups.get(name)
            if group is None:
                continue
            data = item.opts["meshdata"]
            data.setFaceColors(self._colours(group))
            item.meshDataChanged()

    def _gl_options(self) -> dict:
        options = {GL.GL_DEPTH_TEST: True, GL.GL_BLEND: False, GL.GL_CULL_FACE: False}
        if self._wireframe:
            # Faces are pushed back a hair so the edges drawn over them win the depth
            # test instead of stippling in and out of their own surface.
            options[GL.GL_POLYGON_OFFSET_FILL] = True
            options["glPolygonOffset"] = (1.0, 1.0)
        else:
            options[GL.GL_POLYGON_OFFSET_FILL] = False
        return options

    @property
    def highlight(self) -> bool:
        return self._highlight

    def set_highlight(self, on: bool) -> None:
        if self._highlight != on:
            self._highlight = on
            self._recolour()
            self.update()

    @property
    def wireframe(self) -> bool:
        return self._wireframe

    def set_wireframe(self, on: bool) -> None:
        if self._wireframe == on:
            return
        self._wireframe = on
        for item in self._items.values():
            item.opts["drawEdges"] = on
            item.setGLOptions(self._gl_options())
            item.meshDataChanged()
        self.update()

    # ---- furniture ----------------------------------------------------------------------
    def set_grid_visible(self, visible: bool) -> None:
        self.grid.setVisible(visible)

    def set_bed_visible(self, visible: bool) -> None:
        self.bed.setVisible(visible)
        self._fit_grid()

    def set_bed(self, size: tuple[float, float, float], scale: float = 1.0) -> None:
        self.bed.set_size(size, scale)
        self._fit_grid()

    def _fit_grid(self) -> None:
        """The grid covers the model with room around it, and the bed when it is shown."""
        extent = 0.0
        if (bounds := self.bounds(visible_only=False)) is not None:
            lo, hi = bounds
            extent = float(max(hi[0] - lo[0], hi[1] - lo[1])) * 1.6
        if self.bed.visible():
            bx, by, _ = (v / max(self.bed._scale, 1e-6) for v in self.bed.size)
            extent = max(extent, bx, by)
        extent = max(extent, 100.0)
        extent = math.ceil(extent / 20.0) * 20.0
        self.grid.setSize(extent, extent)

    # ---- the camera -------------------------------------------------------------------
    @property
    def orthographic(self) -> bool:
        return self._orthographic

    def set_orthographic(self, on: bool) -> None:
        self._orthographic = on
        self.update()

    def projectionMatrix(self, region, viewport):
        """Perspective as pyqtgraph does it, or a parallel box of the same width at
        the centre of interest — so toggling keeps the subject the same size."""
        if not self._orthographic:
            return super().projectionMatrix(region, viewport)
        x0, y0, w, h = viewport
        dist = self.opts["distance"]
        near, far = dist * 0.001, dist * 1000.0
        r = dist * math.tan(0.5 * math.radians(self.opts["fov"]))
        t = r * h / w
        left = r * ((region[0] - x0) * (2.0 / w) - 1)
        right = r * ((region[0] + region[2] - x0) * (2.0 / w) - 1)
        bottom = t * ((region[1] - y0) * (2.0 / h) - 1)
        top = t * ((region[1] + region[3] - y0) * (2.0 / h) - 1)
        tr = QMatrix4x4()
        tr.ortho(left, right, bottom, top, near, far)
        return tr

    def fit(self, lo: np.ndarray, hi: np.ndarray) -> None:
        """Frame a box: centre on it, back off until its sphere fits the narrower axis."""
        centre = (np.asarray(lo) + np.asarray(hi)) / 2.0
        radius = max(float(np.linalg.norm(np.asarray(hi) - np.asarray(lo))) / 2.0, 1e-3)
        hfov = math.radians(self.opts["fov"])
        w, h = max(1, self.width()), max(1, self.height())
        vfov = 2.0 * math.atan(math.tan(hfov / 2.0) * h / w)
        distance = radius / math.sin(min(hfov, vfov) / 2.0) * 1.08
        self.setCameraPosition(pos=QVector3D(*map(float, centre)), distance=distance)

    def fit_current(self) -> None:
        if (bounds := self.bounds()) is not None:
            self.fit(*bounds)

    def snap(self, view: str, animate: bool = True) -> None:
        """Travel to a named view (see :data:`VIEWS`) rather than cutting to it."""
        elevation, azimuth = VIEWS[view]
        self.set_turntable(False)
        current = (float(self.opts["elevation"]), float(self.opts["azimuth"]))
        # Take the short way round: a 350 degree sweep to move 10 says the wrong thing.
        delta = (azimuth - current[1] + 180.0) % 360.0 - 180.0
        target = (elevation, current[1] + delta)
        if not animate or not self.isVisible():
            self.setCameraPosition(elevation=target[0], azimuth=target[1] % 360.0)
            return
        self._glide.stop()
        self._glide_from, self._glide_to = current, target
        self._glide.setStartValue(0.0)
        self._glide.setEndValue(1.0)
        self._glide.start()

    def _glide_step(self, t: float) -> None:
        (e0, a0), (e1, a1) = self._glide_from, self._glide_to
        self.setCameraPosition(elevation=e0 + (e1 - e0) * t, azimuth=a0 + (a1 - a0) * t)

    def camera(self) -> dict[str, float]:
        centre = self.opts["center"]
        return {
            "azimuth": float(self.opts["azimuth"]),
            "elevation": float(self.opts["elevation"]),
            "distance": float(self.opts["distance"]),
            "cx": float(centre.x()),
            "cy": float(centre.y()),
            "cz": float(centre.z()),
        }

    def set_camera(self, camera: dict[str, float]) -> None:
        self.setCameraPosition(
            pos=QVector3D(float(camera.get("cx", 0.0)), float(camera.get("cy", 0.0)), float(camera.get("cz", 0.0))),
            distance=float(camera.get("distance", self.opts["distance"])),
            elevation=float(camera.get("elevation", self.opts["elevation"])),
            azimuth=float(camera.get("azimuth", self.opts["azimuth"])),
        )

    # ---- the turntable ----------------------------------------------------------------
    @property
    def turntable(self) -> bool:
        return self._turntable.isActive()

    def set_turntable(self, on: bool) -> None:
        if on == self.turntable:
            return
        if on:
            self._glide.stop()
            self._turntable.start()
        else:
            self._turntable.stop()
        self.turntable_changed.emit(on)

    def mousePressEvent(self, ev):
        # Grabbing the view takes it back from the turntable; fighting the timer for
        # the azimuth is the classic auto-orbit annoyance.
        self.set_turntable(False)
        self._glide.stop()
        super().mousePressEvent(ev)

    def wheelEvent(self, ev):
        self._glide.stop()
        super().wheelEvent(ev)
