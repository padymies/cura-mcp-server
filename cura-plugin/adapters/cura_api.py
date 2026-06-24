"""The anti-corruption layer: the ONLY module that touches Cura/Uranium internals.

Everything else in the plugin calls these functions. When a Cura version renames
or moves an internal, this is the single file to fix.

STATUS: VERIFIED against UltiMaker Cura 5.10.0 AND 5.13.0 source (the bundled
``cura/`` + ``UM/`` packages, ``CuraEngineBackend`` and the ``3MFReader`` /
``3MFWriter`` / ``PerObjectSettingsTool`` plugins). Every accessor below was read
from that source. v0.1/Tier-1/Tier-2 are validated live on both versions; Tier 3
(project I/O, variants, group/merge, per-object/mesh) is likewise verified against
both. Known version delta handled here: ``CuraApplication.setloadingWorkspace`` is
5.13+ only (guarded with ``getattr``). One Tier 3 path is deliberately NOT enabled:
``open_project_workspace(mode="replace_active")`` is fail-closed behind a ``# VERIFY:``
(destructive in-place profile override — see that function). Where a behaviour is an
intentional approximation (``_fits_build_volume``'s fallback path) it is noted inline.

All functions here assume they are called on Cura's MAIN THREAD (callers route
through ``bridge.main_thread.run_on_main_thread``), except pure-data reads noted
as thread-agnostic. The load + slice handshakes split work between a main-thread
trigger and a worker-thread wait (see operations/load.py, operations/slice.py).
"""
from __future__ import annotations

import enum
import math
from contextlib import contextmanager
from typing import Callable

from ..errors import (
    ExportFailed,
    InvalidSettingValue,
    LoadFailed,
    NodeNotFound,
    PerExtruderUnsupported,
    UnknownProfile,
    UnknownSetting,
)

# NOTE: import Cura/Uranium lazily inside functions (or guarded at module top) so
# the module can be imported for linting outside Cura.
try:
    from cura.CuraApplication import CuraApplication
except ImportError:  # pragma: no cover - outside Cura
    CuraApplication = None  # type: ignore[assignment]


class SliceState(enum.Enum):
    """Normalized backend states. ``cura_api`` maps Cura's raw state to these."""

    NOT_STARTED = "not_started"
    SLICING = "slicing"
    DONE = "done"          # estimates are valid
    ERROR = "error"        # slicing failed
    DISABLED = "disabled"  # nothing to slice / model outside build volume


# --- application / profile ------------------------------------------------

def get_application():  # noqa: ANN201
    if CuraApplication is None:
        raise RuntimeError("Cura is not available (running outside Cura?).")
    return CuraApplication.getInstance()


def get_active_machine_material() -> tuple[str | None, str | None]:
    """Return (machine_name, material_name) or (None, None) if none active.

    Estimates depend on the active material's density; callers warn when absent.

    5.10-5.13: CuraApplication.getMachineManager() -> MachineManager;
    MachineManager.activeMachine (pyqtProperty) -> Optional[GlobalStack];
    GlobalStack.getName() (ContainerStack); GlobalStack.extruderList ->
    List[ExtruderStack]; ExtruderStack.material -> InstanceContainer.getName().
    """
    app = get_application()
    machine_manager = app.getMachineManager()
    global_stack = machine_manager.activeMachine
    if global_stack is None:
        return (None, None)

    machine_name: str | None = global_stack.getName()

    material_name: str | None = None
    try:
        extruders = global_stack.extruderList
        if extruders:
            material = extruders[0].material
            if material is not None:
                material_name = material.getName()
    except Exception:  # noqa: BLE001 - missing material must not crash status
        material_name = None

    return (machine_name, material_name)


# --- scene / nodes --------------------------------------------------------

def _node_id(node) -> str:  # noqa: ANN001
    """Best-effort stable-ish identifier for a SceneNode."""
    try:
        name = node.getName()  # SceneNode.getName()
        if name:
            return name
    except Exception:  # noqa: BLE001
        pass
    return f"node-{id(node):x}"


def get_active_node():  # noqa: ANN201
    """Return the currently selected/active SceneNode, or a single loaded model.

    5.10-5.13: UM.Scene.Selection.Selection.hasSelection()/getSelectedObject(0);
    otherwise walk app.getController().getScene().getRoot() with
    DepthFirstIterator and keep nodes where callDecoration("isSliceable") is
    truthy (set by SliceableObjectDecorator on loaded printable meshes).
    """
    app = get_application()
    from UM.Scene.Selection import Selection

    if Selection.hasSelection():
        return Selection.getSelectedObject(0)

    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    sliceable = [
        node
        for node in DepthFirstIterator(scene.getRoot())
        if node.callDecoration("isSliceable")
    ]
    if not sliceable:
        raise RuntimeError("No model loaded in the scene.")
    return sliceable[0]


def count_sliceable_nodes() -> int:
    """Number of printable (sliceable) nodes currently on the plate. Thread: main.

    Same scan as ``get_active_node`` (DepthFirstIterator +
    callDecoration("isSliceable")) but returns a count instead of raising, so
    callers can guard against slicing an empty plate.
    """
    app = get_application()
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    return sum(
        1 for node in DepthFirstIterator(scene.getRoot()) if node.callDecoration("isSliceable")
    )


def count_printable_nodes() -> int:
    """Sliceable nodes that are actually INSIDE the build volume. Thread: main.

    The slice guard counts these (not just sliceable ones): a model that is on the
    plate but outside the build area is sliceable yet not printable, and slicing it
    never reaches a terminal backend state — the handshake would hang exactly like
    an empty plate. We refresh each node's flag (checkBoundsAndUpdate) before
    reading isOutsideBuildArea so the count reflects the current placement.
    """
    app = get_application()
    check = getattr(app.getBuildVolume(), "checkBoundsAndUpdate", None)
    count = 0
    for node in _all_sliceable_nodes():
        if callable(check):
            check(node)
        is_outside = getattr(node, "isOutsideBuildArea", None)
        if callable(is_outside) and is_outside():
            continue
        count += 1
    return count


# --- Tier 1: model management (list / find / select / remove / duplicate) --

def _all_sliceable_nodes() -> list:
    """All printable SceneNodes on the active plate. Thread: main.

    5.10-5.13: DepthFirstIterator over the scene root, keeping nodes whose
    ``isSliceable`` decoration is truthy (SliceableObjectDecorator).
    """
    app = get_application()
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    return [n for n in DepthFirstIterator(scene.getRoot()) if n.callDecoration("isSliceable")]


def _find_node_by_id(node_id: str):  # noqa: ANN202
    """Return the sliceable node whose ``_node_id`` matches, or None."""
    for node in _all_sliceable_nodes():
        if _node_id(node) == node_id:
            return node
    return None


def list_nodes() -> list[dict]:
    """All printable nodes as [{node_id, bounds_mm, position_mm}]. Thread: main.

    5.10-5.13: SceneNode.getWorldPosition() -> Vector (the node origin in scene
    mm); bounds via getBoundingBox().
    """
    out: list[dict] = []
    for node in _all_sliceable_nodes():
        pos = node.getWorldPosition()
        out.append(
            {
                "node_id": _node_id(node),
                "bounds_mm": _bounds_mm(node),
                "position_mm": [float(pos.x), float(pos.y), float(pos.z)],
            }
        )
    return out


def select_node(node_id: str) -> dict:
    """Make ``node_id`` the active selection. Thread: main.

    5.10-5.13: UM.Scene.Selection.Selection.clear()/add(node).
    """
    node = _find_node_by_id(node_id)
    if node is None:
        raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
    from UM.Scene.Selection import Selection

    Selection.clear()
    Selection.add(node)
    return {"node_id": _node_id(node), "selected": True}


def remove_node(node_id: str) -> dict:
    """Remove one node from the plate (undoable). Thread: main.

    5.10-5.13: UM.Operations.RemoveSceneNodeOperation.RemoveSceneNodeOperation(
    node).push() (same op clear_build_plate groups); clear the selection after.
    """
    node = _find_node_by_id(node_id)
    if node is None:
        raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
    from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation
    from UM.Scene.Selection import Selection

    RemoveSceneNodeOperation(node).push()
    Selection.clear()
    return {"removed": node_id}


def _unique_name(base: str, taken: set[str]) -> str:
    """A node name derived from ``base`` not already in ``taken``."""
    i = 1
    while True:
        candidate = f"{base} ({i})"
        if candidate not in taken:
            return candidate
        i += 1


def _arrange_nodes(nodes_to_arrange: list, keep_others_fixed: bool) -> None:
    """Place ``nodes_to_arrange`` on the plate via Cura's Nest2DArrange.

    5.10-5.13: cura.Arranging.Nest2DArrange.Nest2DArrange(nodes, build_volume,
    fixed_nodes).arrange() pushes a GroupedOperation (RotateOp + TranslateOp per
    node). When ``keep_others_fixed`` is set, every other sliceable node is passed
    as a fixed node so only the given ones move (used by duplicate).
    """
    if not nodes_to_arrange:
        return
    app = get_application()
    from cura.Arranging.Nest2DArrange import Nest2DArrange

    fixed: list = []
    if keep_others_fixed:
        moving = {id(n) for n in nodes_to_arrange}
        fixed = [n for n in _all_sliceable_nodes() if id(n) not in moving]
    Nest2DArrange(nodes_to_arrange, app.getBuildVolume(), fixed).arrange()


def duplicate_node(node_id: str, count: int = 1) -> dict:
    """Duplicate ``node_id`` ``count`` times; place copies in free plate spots.

    Synchronous (no async job): mirrors what cura.MultiplyObjectsJob does —
    ``copy.deepcopy(node)`` + AddSceneNodeOperation grouped onto the operation
    stack — but on the main thread so the result is ready on return. Copies are
    renamed to keep ``node_id`` unique, then arranged with the existing models
    held fixed. (The source node's ZOffsetDecorator was already dropped by
    arrange_loaded_node, so copies don't get sunk by PlatformPhysics.)
    """
    node = _find_node_by_id(node_id)
    if node is None:
        raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
    count = max(1, int(count))

    import copy

    from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation
    from UM.Operations.GroupedOperation import GroupedOperation

    app = get_application()
    parent = node.getParent() or app.getController().getScene().getRoot()
    taken = {_node_id(n) for n in _all_sliceable_nodes()}

    operation = GroupedOperation()
    copies: list = []
    for _ in range(count):
        new_node = copy.deepcopy(node)
        new_id = _unique_name(node_id, taken)
        new_node.setName(new_id)
        # BuildPlateDecorator.__deepcopy__ resets the plate number to -1, so the
        # copy would not render on the active plate (only its convex-hull shadow
        # shows). Restore the source's plate number; the decorator's setter also
        # propagates to children. Mirrors cura.MultiplyObjectsJob.
        build_plate_number = node.callDecoration("getBuildPlateNumber")
        if build_plate_number is not None:
            new_node.callDecoration("setBuildPlateNumber", build_plate_number)
        taken.add(new_id)
        operation.addOperation(AddSceneNodeOperation(new_node, parent))
        copies.append(new_node)
    operation.push()

    _arrange_nodes(copies, keep_others_fixed=True)

    return {
        "original": node_id,
        "created": [_node_id(n) for n in copies],
        "count": len(copies),
    }


def arrange_all() -> dict:
    """Auto-arrange every model on the plate (Cura's own Nest2DArrange).

    Returns the number of models arranged.
    """
    nodes = _all_sliceable_nodes()
    if not nodes:
        return {"arranged": 0}
    _arrange_nodes(nodes, keep_others_fixed=False)
    return {"arranged": len(nodes)}


# --- Tier 1: transforms (scale / mirror / move / center / scale_to_fit) ----

def _machine_dims() -> tuple[float, float, float]:
    """Active machine (width=X, height=vertical, depth=front-back) in mm.

    5.10-5.13: GlobalStack.getProperty("machine_width"/"machine_height"/
    "machine_depth", "value"). Matches the axis convention in _fits_build_volume.
    """
    stack = get_application().getMachineManager().activeMachine
    width = float(stack.getProperty("machine_width", "value"))
    height = float(stack.getProperty("machine_height", "value"))
    depth = float(stack.getProperty("machine_depth", "value"))
    return width, height, depth


def _refresh_and_result(node) -> dict:  # noqa: ANN001
    """Refresh the build-area flag, then summarise the node after a transform."""
    check = getattr(get_application().getBuildVolume(), "checkBoundsAndUpdate", None)
    if callable(check):
        check(node)
    pos = node.getWorldPosition()
    return {
        "node_id": _node_id(node),
        "bounds_mm": _bounds_mm(node),
        "position_mm": [float(pos.x), float(pos.y), float(pos.z)],
        "fits_build_volume": _fits_build_volume(node),
    }


def _require_node(node_id: str):  # noqa: ANN202
    node = _find_node_by_id(node_id)
    if node is None:
        raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
    return node


def scale_node(node_id: str, sx: float, sy: float, sz: float) -> dict:
    """Scale a node by per-axis multipliers of its CURRENT scale, then reseat.

    5.10-5.13: UM.Operations.ScaleOperation.ScaleOperation(node, Vector,
    set_scale=True) -> setScale(Vector, World) (absolute scale factor; 1.0 =
    original mesh size). We multiply the current scale by the factors so callers
    get "scale relative to current size", then drop to the plate (scaling shifts
    the bottom).
    """
    node = _require_node(node_id)
    from UM.Math.Vector import Vector
    from UM.Operations.ScaleOperation import ScaleOperation

    cur = node.getScale()
    new_scale = Vector(cur.x * sx, cur.y * sy, cur.z * sz)
    ScaleOperation(node, new_scale, set_scale=True).push()
    _drop_to_plate(node)
    return _refresh_and_result(node)


def mirror_node(node_id: str, axis: str) -> dict:
    """Mirror a node about ``axis`` (x/y/z), around its own centre.

    5.10-5.13: UM.Operations.MirrorOperation.MirrorOperation(node, Vector(diag of
    1/-1), mirror_around_center=True).
    """
    node = _require_node(node_id)
    from UM.Math.Vector import Vector
    from UM.Operations.MirrorOperation import MirrorOperation

    vectors = {"x": Vector(-1, 1, 1), "y": Vector(1, -1, 1), "z": Vector(1, 1, -1)}
    MirrorOperation(node, vectors[axis], mirror_around_center=True).push()
    _drop_to_plate(node)
    return _refresh_and_result(node)


def move_node(node_id: str, x: float, y: float, z: float, relative: bool) -> dict:
    """Translate a node. Absolute (``relative=False``) sets the node origin to
    (x,y,z); relative adds. Intentionally does NOT reseat on the plate — this is
    the raw move (used to push a model outside the build volume on purpose).

    5.10-5.13: UM.Operations.TranslateOperation.TranslateOperation(node, Vector,
    set_position=<absolute>) -> setPosition(World) / translate(World).
    """
    node = _require_node(node_id)
    from UM.Math.Vector import Vector
    from UM.Operations.TranslateOperation import TranslateOperation

    TranslateOperation(node, Vector(x, y, z), set_position=not relative).push()
    return _refresh_and_result(node)


def center_node(node_id: str) -> dict:
    """Centre a node on the plate (X/Z to the build-volume centre) and drop it to
    Y=0. Same placement arrange_loaded_node applies on import.
    """
    node = _require_node(node_id)
    from UM.Math.Vector import Vector
    from UM.Operations.TranslateOperation import TranslateOperation

    bbox = node.getBoundingBox()
    if bbox is not None:
        bvb = get_application().getBuildVolume().getBoundingBox()
        target_x = bvb.center.x if bvb is not None else 0.0
        target_z = bvb.center.z if bvb is not None else 0.0
        delta = Vector(target_x - bbox.center.x, -bbox.bottom, target_z - bbox.center.z)
        TranslateOperation(node, delta).push()
    return _refresh_and_result(node)


def scale_to_fit_node(node_id: str) -> dict:
    """Uniform-scale a node DOWN so it fits the build volume (no-op if it already
    fits). Shrink-only, with a 2% margin; then reseat and centre.
    """
    node = _require_node(node_id)
    size = _bounds_mm(node)  # [X, vertical, depth]
    if len(size) == 3 and all(s > 0 for s in size):
        width, height, depth = _machine_dims()
        factor = min(width / size[0], height / size[1], depth / size[2]) * 0.98
        if factor < 1.0:
            from UM.Math.Vector import Vector
            from UM.Operations.ScaleOperation import ScaleOperation

            cur = node.getScale()
            new_scale = Vector(cur.x * factor, cur.y * factor, cur.z * factor)
            ScaleOperation(node, new_scale, set_scale=True).push()
            _drop_to_plate(node)
            return center_node(node_id)
    return _refresh_and_result(node)


def _bounds_mm(node) -> list[float]:  # noqa: ANN001
    """Return [x, y, z] bounding-box size in mm, or [] if unavailable.

    5.10-5.13: SceneNode.getBoundingBox() -> AxisAlignedBox with .width (X extent),
    .height (Y/vertical extent), .depth (Z extent), all in mm.
    """
    try:
        bbox = node.getBoundingBox()
        if bbox is None:
            return []
        return [float(bbox.width), float(bbox.height), float(bbox.depth)]
    except Exception:  # noqa: BLE001
        return []


def _fits_build_volume(node) -> bool:  # noqa: ANN001
    """Whether the node currently fits the build volume.

    5.10-5.13: CuraSceneNode.isOutsideBuildArea() is Cura's authoritative per-node
    flag (set by BuildVolume.checkBoundsAndUpdate during load). We use it when
    present. Fallback (non-CuraSceneNode): compare the bounding box against the
    machine dimensions, accounting for Uranium's Y-up axes vs Cura's settings
    (machine_width=X, machine_depth=Y/front-back, machine_height=Z/vertical;
    bbox.height is the vertical/Y extent, bbox.depth is the Z extent).
    """
    try:
        is_outside = getattr(node, "isOutsideBuildArea", None)
        if callable(is_outside):
            return not bool(is_outside())

        size = _bounds_mm(node)  # [x, y_vertical, z_depth]
        if len(size) != 3:
            return True  # unknown → don't claim it fails
        stack = get_application().getMachineManager().activeMachine
        if stack is None:
            return True
        width = float(stack.getProperty("machine_width", "value"))    # X
        depth = float(stack.getProperty("machine_depth", "value"))    # Y (front-back)
        height = float(stack.getProperty("machine_height", "value"))  # Z (vertical)
        return size[0] <= width and size[1] <= height and size[2] <= depth
    except Exception:  # noqa: BLE001
        return True


def resolve_loaded_node() -> dict:
    """Summarise the active/loaded node. Call only after a load has settled.

    Returns {node_id, fits_build_volume, bounds_mm}.
    """
    node = get_active_node()
    return {
        "node_id": _node_id(node),
        "fits_build_volume": _fits_build_volume(node),
        "bounds_mm": _bounds_mm(node),
    }


# --- model load (asynchronous; see operations/load.py) --------------------

def subscribe_file_completed(callback: Callable[[str], None]) -> object:
    """Connect ``callback`` to CuraApplication.fileCompleted (pyqtSignal(str)).

    5.10-5.13: ``readLocalFile`` runs a ReadMeshJob and returns immediately; the
    mesh is added to the scene (AddSceneNodeOperation) inside ``_readMeshFinished``
    on the main thread, and ``fileCompleted`` is emitted AFTER that add + arrange.
    ``fileLoaded`` fires earlier — before the node is in the scene — so we wait on
    ``fileCompleted``. Return an opaque token for ``unsubscribe_file_completed``.
    """
    app = get_application()
    app.fileCompleted.connect(callback)
    return (app, callback)


def unsubscribe_file_completed(token: object) -> None:
    """Disconnect a previously subscribed fileCompleted callback."""
    app, callback = token  # type: ignore[misc]
    app.fileCompleted.disconnect(callback)


def trigger_load(path: str) -> None:
    """Start an asynchronous mesh load. Returns immediately (job runs in background).

    Path is ALREADY sandbox-validated by operations.load before reaching here.
    5.10-5.13: CuraApplication.readLocalFile(QUrl, project_mode=None,
    add_to_recent_files=True).
    """
    from PyQt6.QtCore import QUrl

    app = get_application()
    app.readLocalFile(QUrl.fromLocalFile(path), add_to_recent_files=False)


def arrange_loaded_node(node=None) -> None:  # noqa: ANN001
    """Center a freshly loaded node on the build plate and drop it to the plate.

    A plain ``readLocalFile`` of a ``.3mf`` does NOT auto-arrange the model:
    CuraApplication._readMeshFinished (5.10.0) only appends STL/OBJ meshes (and
    project-as-model loads) to ``nodes_to_arrange``; a 3MF keeps the file's own
    coordinates and can land off-plate (e.g. the 3D-Builder ``Cubo.3mf`` lands off
    the Ender 3 S1 bed), so it reads as outside the build volume and slicing is
    disabled.

    For the single-model v1 flow we place the model DETERMINISTICALLY at the build
    plate centre instead of running Cura's ``Nest2DArrange``: the nester applies a
    RELATIVE placement tuned for freshly-imported-at-origin STL meshes and ejects a
    single off-origin 3MF to a bed corner (observed: a +110/-110 mm shove on a
    220x220 bed). We translate the node's bounding-box centre to the build-volume
    centre in X/Z and drop its bottom onto the plate (Y=0). Reading the build
    volume's own bounding box respects the machine's plate position
    (machine_center_is_zero). Landing at bottom=0 also matches Cura's
    PlatformPhysics auto-drop target, so its delayed timer move is a no-op (no
    revert).

    5.10-5.13: UM.Operations.TranslateOperation.TranslateOperation(node, Vector,
    set_position=False) is a relative world-space move pushed onto the operation
    stack (undoable + triggers a re-slice); AxisAlignedBox.center / .bottom give
    the node's current placement; BuildVolume.getBoundingBox() / checkBoundsAndUpdate
    give the plate position and refresh isOutsideBuildArea() synchronously.

    Thread: MAIN (pushes an operation / mutates the scene).
    """
    app = get_application()
    if node is None:
        node = get_active_node()

    bbox = node.getBoundingBox()
    if bbox is None:
        return  # without bounds there is nothing reliable to center

    from UM.Math.Vector import Vector
    from UM.Operations.TranslateOperation import TranslateOperation

    # Plate centre in scene coordinates (handles machine_center_is_zero by reading
    # the actual build-volume position). Fall back to the scene origin if absent.
    build_volume = app.getBuildVolume()
    bv_bbox = build_volume.getBoundingBox() if build_volume is not None else None
    target_x = bv_bbox.center.x if bv_bbox is not None else 0.0
    target_z = bv_bbox.center.z if bv_bbox is not None else 0.0

    # One relative move: centre the bbox in X/Z, drop its bottom onto the plate.
    delta = Vector(
        target_x - bbox.center.x,
        -bbox.bottom,
        target_z - bbox.center.z,
    )
    TranslateOperation(node, delta).push()

    # The 3MF reader can attach a ZOffsetDecorator (the amount a model was "sunk"
    # below the plate, baked into the file). Cura's PlatformPhysics re-applies it
    # ~1.5s after load as move.y = -bbox.bottom + z_offset, which drags our
    # freshly-placed model below the plate (observed: a -62.998 mm sink that makes
    # the slice fail). For a normal place-on-plate we drop that offset, so physics
    # settles to move.y = 0 and the model stays where we put it.
    from cura.Scene.ZOffsetDecorator import ZOffsetDecorator

    if node.getDecorator(ZOffsetDecorator) is not None:
        node.removeDecorator(ZOffsetDecorator)

    # Synchronously refresh the per-node outside-build-area flag so a subsequent
    # resolve_loaded_node() returns the post-center truth.
    check = getattr(build_volume, "checkBoundsAndUpdate", None)
    if callable(check):
        check(node)


def _drop_to_plate(node) -> None:  # noqa: ANN001
    """Drop a node so its bounding-box bottom rests on the plate (Y=0).

    Replicates Cura's automatic drop-down (PlatformPhysics) SYNCHRONOUSLY, so the
    model is settled the moment the call returns instead of racing the physics
    timer that only fires ~1.5s later. Without this, slicing right after a
    transform (e.g. a rotate that tips the model partly below the plate) sees an
    off-plate model and the slice fails. Pushes a relative TranslateOperation;
    leaving the bottom at 0 also makes the later physics pass a no-op.
    """
    bbox = node.getBoundingBox()
    if bbox is None or abs(bbox.bottom) <= 1e-4:
        return

    from UM.Math.Vector import Vector
    from UM.Operations.TranslateOperation import TranslateOperation

    TranslateOperation(node, Vector(0, -bbox.bottom, 0)).push()


# --- Tier 1: machine info / snapshot / export -----------------------------

def get_machine_info() -> dict:
    """Active machine name, build volume (mm), nozzle size, extruder count.

    5.10-5.13: GlobalStack.getName(); machine_width/depth/height via getProperty;
    nozzle from the first ExtruderStack's machine_nozzle_size; extruderList length.
    """
    stack = get_application().getMachineManager().activeMachine
    if stack is None:
        return {
            "machine_name": None,
            "build_volume_mm": {"width": 0.0, "depth": 0.0, "height": 0.0},
            "nozzle_size_mm": None,
            "extruder_count": 0,
        }

    width, height, depth = _machine_dims()  # width=X, height=vertical, depth=front-back
    extruders = list(getattr(stack, "extruderList", []) or [])

    nozzle: float | None = None
    try:
        source = extruders[0] if extruders else stack
        nozzle = float(source.getProperty("machine_nozzle_size", "value"))
    except Exception:  # noqa: BLE001 - nozzle is informational
        nozzle = None

    return {
        "machine_name": stack.getName(),
        "build_volume_mm": {"width": width, "depth": depth, "height": height},
        "nozzle_size_mm": nozzle,
        "extruder_count": len(extruders),
    }


def snapshot_png(width: int = 600, height: int = 600) -> dict:
    """Render the current plate to a PNG, base64-encoded. Thread: main.

    5.10-5.13: cura.Snapshot.Snapshot.snapshot(width, height) -> QImage | None
    (None on an empty plate). Encode to PNG bytes via a QBuffer, exactly as the
    3MF/UFP writers do (img.save(buffer, "PNG")), then base64.
    """
    import base64

    from cura.Snapshot import Snapshot

    image = Snapshot.snapshot(width, height)
    if image is None:
        return {"image_base64": None, "width": width, "height": height}

    from PyQt6.QtCore import QBuffer

    buffer = QBuffer()
    buffer.open(QBuffer.OpenModeFlag.ReadWrite)
    image.save(buffer, "PNG")
    encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
    buffer.close()
    return {"image_base64": encoded, "width": width, "height": height}


_EXPORT_MIME = {
    "stl": "model/stl",
    "3mf": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
}


def export_mesh(path: str, fmt: str, node_id: str | None) -> dict:
    """Write the target mesh(es) to ``path`` in ``fmt`` (stl|3mf). Thread: main.

    Path is ALREADY output-sandbox-validated by operations.export.
    5.10-5.13: app.getMeshFileHandler().getWriterByMimeType(mime) -> MeshWriter;
    writer.write(stream, nodes, MeshWriter.OutputMode.BinaryMode) with a binary
    file stream. Synchronous (we call write directly rather than via WriteFileJob).
    """
    app = get_application()
    if node_id in (None, "all"):
        nodes = _all_sliceable_nodes()
    else:
        node = _find_node_by_id(node_id)
        if node is None:
            raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
        nodes = [node]
    if not nodes:
        raise ExportFailed("No models on the plate to export.")

    mime = _EXPORT_MIME.get(fmt)
    if mime is None:
        raise ExportFailed(f"Unsupported export format '{fmt}'. Use stl or 3mf.")
    writer = app.getMeshFileHandler().getWriterByMimeType(mime)
    if writer is None:
        raise ExportFailed(f"No mesh writer available for '{fmt}'.")

    from UM.Mesh.MeshWriter import MeshWriter

    try:
        with open(path, "wb") as stream:
            ok = writer.write(stream, nodes, MeshWriter.OutputMode.BinaryMode)
    except OSError as exc:
        raise ExportFailed(f"Could not write '{path}': {exc}") from exc
    if not ok:
        raise ExportFailed(f"The {fmt} writer failed to export.")

    return {"path": path, "format": fmt, "models": len(nodes)}


def _axis_vector(axis: str):  # noqa: ANN201
    from UM.Math.Vector import Vector  # Vector.Unit_X/Y/Z are class constants.

    return {"x": Vector.Unit_X, "y": Vector.Unit_Y, "z": Vector.Unit_Z}[axis]


def apply_rotation(axis: str, degrees: float) -> dict:
    """Rotate the active node about ``axis``. Return {node_id, rotation_deg}.

    rotation_deg reports the APPLIED delta for this call, not the node's absolute
    Euler orientation.

    5.10-5.13: UM.Operations.RotateOperation.RotateOperation(node, Quaternion);
    Quaternion.fromAngleAxis(angle_radians, Vector); Operation.push() pushes onto
    the application operation stack (integrates undo/redo + triggers a re-slice).
    """
    node = get_active_node()
    from UM.Math.Quaternion import Quaternion
    from UM.Operations.RotateOperation import RotateOperation

    rotation = Quaternion.fromAngleAxis(math.radians(degrees), _axis_vector(axis))
    RotateOperation(node, rotation).push()

    # Re-seat on the plate (a tilt can push the model partly below it), matching
    # Cura's auto-drop, so a following slice sees a settled, on-plate model.
    _drop_to_plate(node)

    return {"node_id": _node_id(node), "rotation_deg": {axis: float(degrees)}}


def lay_flat() -> dict:
    """Lay the active node flat. Return {node_id, rotation_deg}.

    5.10-5.13: UM.Operations.LayFlatOperation.LayFlatOperation(node). Its
    ``process()`` computes the lay-flat orientation (lowest-three-vertices
    heuristic) and mutates the node; ``push()`` then commits it via the operation
    stack (redo() re-applies the computed orientation + drops to the plate with a
    GravityOperation). This is exactly the sequence Cura's own lay-flat tool uses.
    """
    node = get_active_node()
    from UM.Operations.LayFlatOperation import LayFlatOperation

    operation = LayFlatOperation(node)
    operation.process()
    operation.push()

    return {"node_id": _node_id(node), "rotation_deg": {}}


def reset_orientation() -> dict:
    """Reset the active node to its original orientation. Return {node_id, rotation_deg}.

    5.10-5.13: UM.Operations.SetTransformOperation.SetTransformOperation(
    node, translation=None, orientation=Quaternion(), ...) resets rotation to
    identity through the operation stack (so undo + re-slice fire).
    """
    node = get_active_node()
    from UM.Math.Quaternion import Quaternion
    from UM.Operations.SetTransformOperation import SetTransformOperation

    SetTransformOperation(node, None, Quaternion()).push()

    return {"node_id": _node_id(node), "rotation_deg": {"x": 0.0, "y": 0.0, "z": 0.0}}


# --- build plate ----------------------------------------------------------

def clear_build_plate() -> int:
    """Remove all printable models from the active build plate. Return the count.

    5.10-5.13: mirrors what CuraApplication._removeNodesWithLayerData (Cura's own
    "Clear Build Plate"/deleteAll path) does — collect sliceable SceneNodes via
    DepthFirstIterator + callDecoration("isSliceable") and remove them in a single
    GroupedOperation of RemoveSceneNodeOperation pushed onto the operation stack,
    so the clear is undoable and resets the slice state (via sceneChanged). We
    build the operation explicitly rather than calling CuraApplication.deleteAll()
    because deleteAll() returns no count, and FR-CP-1 needs the number removed.
    """
    app = get_application()
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    nodes = [
        node
        for node in DepthFirstIterator(scene.getRoot())
        if node.callDecoration("isSliceable")
    ]
    if not nodes:
        return 0

    from UM.Operations.GroupedOperation import GroupedOperation
    from UM.Operations.RemoveSceneNodeOperation import RemoveSceneNodeOperation

    operation = GroupedOperation()
    for node in nodes:
        operation.addOperation(RemoveSceneNodeOperation(node))
        scene.sceneChanged.emit(node)
    operation.push()

    from UM.Scene.Selection import Selection

    Selection.clear()
    return len(nodes)


# --- slicing backend (the async part) -------------------------------------

def get_backend_state() -> SliceState:
    """Current backend state as a normalized SliceState. Thread: main.

    5.10-5.13: UM.Backend.Backend keeps the live state in the private
    ``_backend_state`` (a BackendState); neither Backend nor CuraEngineBackend
    exposes a public getter in either version (QML tracks it via the
    ``backendStateChange`` signal). We read it directly here — encapsulated, which
    is exactly what this anti-corruption layer is for — and map it through
    ``_map_backend_state``. Falls back to NOT_STARTED if the attribute is absent.
    """
    backend = get_application().getBackend()
    raw = getattr(backend, "_backend_state", None)
    if raw is None:
        return SliceState.NOT_STARTED
    return _map_backend_state(raw)


def start_slice() -> None:
    """Force a fresh slice of the current scene.

    5.10-5.13: app.getBackend() -> CuraEngineBackend; forceSlice() does
    markSliceAll() + slice(), so a forced slice transitions NotStarted/Done ->
    Processing -> Done (each transition emits backendStateChange).
    """
    app = get_application()
    backend = app.getBackend()
    backend.forceSlice()


def subscribe_backend_state(callback: Callable[[SliceState], None]) -> object:
    """Connect ``callback`` to the backend state-change signal.

    The callback receives a normalized ``SliceState`` on each transition. Return
    an opaque token to pass to ``unsubscribe_backend_state``.

    5.10-5.13: CuraEngineBackend.backendStateChange is a UM.Signal.Signal (NOT a Qt
    signal); it emits a BackendState and fires on the main thread (from
    Backend.setState, which only emits on an actual transition).
    """
    app = get_application()
    backend = app.getBackend()

    def _wrapper(raw) -> None:  # noqa: ANN001 - raw is a BackendState
        callback(_map_backend_state(raw))

    backend.backendStateChange.connect(_wrapper)
    # Return both the backend and our wrapper so we can disconnect the exact slot
    # (and keep a strong ref to the wrapper for the wait's duration).
    return (backend, _wrapper)


def unsubscribe_backend_state(token: object) -> None:
    """Disconnect a previously subscribed backend-state callback."""
    backend, wrapper = token  # type: ignore[misc]
    backend.backendStateChange.disconnect(wrapper)


def _map_backend_state(raw) -> SliceState:  # noqa: ANN001
    """Translate Cura's raw backend state into a normalized SliceState.

    5.10-5.13: UM.Backend.Backend.BackendState (IntEnum): NotStarted=1, Processing=2,
    Done=3, Error=4, Disabled=5. The signal already delivers a BackendState, so we
    map by member directly (no integer guessing).
    """
    try:
        from UM.Backend.Backend import BackendState

        state = raw if isinstance(raw, BackendState) else BackendState(raw)
        mapping = {
            BackendState.NotStarted: SliceState.NOT_STARTED,
            BackendState.Processing: SliceState.SLICING,
            BackendState.Done: SliceState.DONE,
            BackendState.Error: SliceState.ERROR,
            BackendState.Disabled: SliceState.DISABLED,
        }
        return mapping.get(state, SliceState.NOT_STARTED)
    except Exception:  # noqa: BLE001 - enum import/shape differs on an unexpected build
        fallback = {
            1: SliceState.NOT_STARTED,
            2: SliceState.SLICING,
            3: SliceState.DONE,
            4: SliceState.ERROR,
            5: SliceState.DISABLED,
        }
        try:
            return fallback.get(int(raw), SliceState.NOT_STARTED)
        except (TypeError, ValueError):
            return SliceState.NOT_STARTED


# --- estimates ------------------------------------------------------------

def _duration_to_seconds(duration) -> int:  # noqa: ANN001
    """Convert a Cura Duration (.days/.hours/.minutes/.seconds) to whole seconds."""
    if duration is None:
        return 0
    try:
        days = getattr(duration, "days", 0) or 0
        hours = getattr(duration, "hours", 0) or 0
        minutes = getattr(duration, "minutes", 0) or 0
        seconds = getattr(duration, "seconds", 0) or 0
        # Clamp: an uninitialised PrintInformation can yield negative components
        # (observed -90061s); never surface a negative duration.
        return max(0, int(days * 86400 + hours * 3600 + minutes * 60 + seconds))
    except Exception:  # noqa: BLE001
        return 0


def read_print_information() -> dict:
    """Read material/time estimates from PrintInformation. Thread: main.

    Return:
        {
          "extruders": [{"weight_g": float, "length_m": float, "cost": float|None}, ...],
          "total_weight_g": float,
          "total_length_m": float,
          "print_time_seconds": int,
        }

    5.10-5.13: CuraApplication.getPrintInformation() -> PrintInformation;
    materialWeights/materialLengths/materialCosts are QVariantList (per extruder);
    currentPrintTime -> Duration.
    """
    app = get_application()
    pi = app.getPrintInformation()

    weights = list(getattr(pi, "materialWeights", []) or [])
    lengths = list(getattr(pi, "materialLengths", []) or [])
    costs = list(getattr(pi, "materialCosts", []) or [])

    extruders: list[dict] = []
    for i in range(max(len(weights), len(lengths))):
        weight = float(weights[i]) if i < len(weights) else 0.0
        length = float(lengths[i]) if i < len(lengths) else 0.0
        cost = float(costs[i]) if i < len(costs) and costs[i] is not None else None
        extruders.append({"weight_g": weight, "length_m": length, "cost": cost})

    return {
        "extruders": extruders,
        "total_weight_g": float(sum(weights)) if weights else 0.0,
        "total_length_m": float(sum(lengths)) if lengths else 0.0,
        "print_time_seconds": _duration_to_seconds(getattr(pi, "currentPrintTime", None)),
    }


# --- Tier 2: settings (read / meta / write / reset) -----------------------

@contextmanager
def _suppress_profile_override_dialog():  # noqa: ANN202
    """Make profile-change ops (machine/material/variant/quality) non-interactive.

    MachineManager.setActiveMachine/setVariant/setMaterial/setQualityGroup call
    CuraApplication.discardOrKeepProfileChanges(), which pops the BLOCKING "Discard
    or Keep Changes" modal when ``cura/choice_on_profile_override`` == "always_ask"
    (the default) AND there are pending user settings. Over the HTTP bridge that
    modal would hang the call, so we force "always_keep" for the duration (which
    PRESERVES the user's overrides across the switch) and restore the prior choice.
    5.10-5.13: the preference key + the always_keep short-circuit are identical.
    """
    prefs = get_application().getPreferences()
    key = "cura/choice_on_profile_override"
    previous = prefs.getValue(key)
    prefs.setValue(key, "always_keep")
    try:
        yield
    finally:
        prefs.setValue(key, previous)


def _global_stack():  # noqa: ANN202
    """The active machine's global container stack, or raise if none.

    5.10-5.13: CuraApplication.getGlobalContainerStack() -> GlobalStack | None.
    """
    stack = get_application().getGlobalContainerStack()
    if stack is None:
        raise UnknownSetting("No active machine; load/select a printer first.")
    return stack


def _setting_exists(stack, key: str) -> bool:  # noqa: ANN001
    """Whether ``key`` is a real setting in the active machine definition.

    5.10-5.13: DefinitionContainer.findDefinitions(key=...) is the authoritative
    existence check (returns [] for unknown keys).
    """
    try:
        return bool(stack.definition.findDefinitions(key=key))
    except Exception:  # noqa: BLE001 - fall back to the stack's key set
        try:
            return key in stack.getAllKeys()
        except Exception:  # noqa: BLE001
            return False


def _coerce_value(setting_type: str, value):  # noqa: ANN001, ANN201
    """Parse ``value`` to the setting's declared type, or raise InvalidSettingValue.

    Pure (no Cura) so it is unit-testable. Handles the common scalar types; other
    types pass through unchanged (best effort).
    """
    try:
        if setting_type == "float":
            return float(value)
        if setting_type == "int":
            return int(float(value)) if isinstance(value, str) else int(value)
        if setting_type == "bool":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in ("true", "1", "yes", "on")
            return bool(value)
        if setting_type in ("str", "enum"):
            return str(value)
    except (TypeError, ValueError) as exc:
        raise InvalidSettingValue(
            f"Value {value!r} is not a valid {setting_type}."
        ) from exc
    return value


def _extruder_stack_or_none():  # noqa: ANN202
    """The active extruder stack, or None if unavailable (e.g. outside Cura).

    5.10-5.13: cura.Settings.ExtruderManager.getInstance().getActiveExtruderStack().
    """
    try:
        from cura.Settings.ExtruderManager import ExtruderManager

        return ExtruderManager.getInstance().getActiveExtruderStack()
    except Exception:  # noqa: BLE001
        return None


def _target_stack(stack, key: str, *, require_extruder: bool = False):  # noqa: ANN001, ANN202
    """Where a setting's value lives: the active extruder for per-extruder keys,
    else the global stack. Cura marks many per-extruder settings (infill, speeds,
    temperatures) ``settable_per_extruder`` even on single-extruder machines, so
    those must be read/written on the extruder stack — the same place the UI uses.
    """
    if bool(stack.getProperty(key, "settable_per_extruder")):
        extruder = _extruder_stack_or_none()
        if extruder is not None:
            return extruder
        if require_extruder:
            raise PerExtruderUnsupported(
                f"'{key}' is a per-extruder setting and no active extruder is available."
            )
    return stack


def get_setting(key: str) -> dict:
    """Resolved value of a setting + its type/unit. Raise UnknownSetting if absent.

    5.10-5.13: getProperty(key, "value"/"type"/"unit"); per-extruder values are
    read from the active extruder stack. The value is resolved through the whole
    container stack (definition→quality→material→user).
    """
    stack = _global_stack()
    if not _setting_exists(stack, key):
        raise UnknownSetting(f"Unknown setting '{key}'.")
    target = _target_stack(stack, key)
    return {
        "key": key,
        "value": target.getProperty(key, "value"),
        "type": stack.getProperty(key, "type"),
        "unit": stack.getProperty(key, "unit"),
    }


def set_setting(key: str, value) -> dict:  # noqa: ANN001
    """Write a GLOBAL setting as a user override, validated, then re-read it.

    Validates (a) the key exists, (b) the value parses to the setting's type,
    (c) numeric values fall within minimum_value/maximum_value, (d) enum values are
    in the options. Per-extruder settings are refused (v1 handles global only).

    5.10-5.13: GlobalStack.setProperty(key, "value", v) routes to the userChanges
    container (CuraContainerStack hardcodes the UserChanges index) — the same place
    the Cura UI writes overrides. After the write Cura auto-triggers a re-slice.
    """
    stack = _global_stack()
    if not _setting_exists(stack, key):
        raise UnknownSetting(f"Unknown setting '{key}'.")

    setting_type = stack.getProperty(key, "type")
    coerced = _coerce_value(setting_type, value)

    if isinstance(coerced, (int, float)) and not isinstance(coerced, bool):
        minimum = stack.getProperty(key, "minimum_value")
        maximum = stack.getProperty(key, "maximum_value")
        if minimum is not None and coerced < float(minimum):
            raise InvalidSettingValue(f"{key}={coerced} is below the minimum {minimum}.")
        if maximum is not None and coerced > float(maximum):
            raise InvalidSettingValue(f"{key}={coerced} is above the maximum {maximum}.")

    options = stack.getProperty(key, "options")
    if options and coerced not in options:
        raise InvalidSettingValue(
            f"{key}={coerced!r} is not a valid option. Allowed: {sorted(options)}."
        )

    # Per-extruder settings must be written to the active extruder's user changes.
    target = _target_stack(stack, key, require_extruder=True)
    target.setProperty(key, "value", coerced)
    return {"key": key, "value": target.getProperty(key, "value"), "type": setting_type}


def reset_setting(key: str) -> dict:
    """Remove a user override for ``key``, reverting to the profile value.

    5.10-5.13: GlobalStack.userChanges.removeInstance(key) (no-op if no override).
    """
    stack = _global_stack()
    if not _setting_exists(stack, key):
        raise UnknownSetting(f"Unknown setting '{key}'.")
    target = _target_stack(stack, key)
    target.userChanges.removeInstance(key)
    return {
        "key": key,
        "value": target.getProperty(key, "value"),
        "type": stack.getProperty(key, "type"),
    }


def set_supports(enabled: bool, placement: str | None) -> dict:
    """Toggle support generation and (optionally) its placement.

    5.10-5.13: global settings ``support_enable`` (bool) and ``support_type``
    (enum: buildplate|everywhere). Routed through the validated set_setting.
    """
    result = set_setting("support_enable", bool(enabled))
    placement_value = None
    if enabled and placement:
        placement_value = set_setting("support_type", placement)["value"]
    return {"support_enable": result["value"], "support_type": placement_value}


def set_quality_preset(preset: str) -> dict:
    """Switch the active quality preset (draft|normal|fine|…).

    5.10-5.13: cura.Machines.ContainerTree.getInstance().getCurrentQualityGroups()
    -> {quality_type: QualityGroup}; MachineManager.setQualityGroupByQualityType.
    """
    from cura.Machines.ContainerTree import ContainerTree

    groups = ContainerTree.getInstance().getCurrentQualityGroups()
    available = {qt: g for qt, g in groups.items() if getattr(g, "is_available", True)}

    # Match the preset against the quality_type ("standard") OR the display name
    # ("Standard") — machines name presets differently (Ender 3 S1 uses
    # low/standard/super/adaptive, not draft/normal/fine).
    chosen = None
    for quality_type, group in available.items():
        display = (group.getName() or "").lower()
        if preset in (quality_type.lower(), display):
            chosen = quality_type
            break
    if chosen is None:
        options = sorted(f"{qt} ({g.getName()})" for qt, g in available.items())
        raise UnknownProfile(f"Unknown quality '{preset}'. Available: {options}.")

    with _suppress_profile_override_dialog():
        get_application().getMachineManager().setQualityGroupByQualityType(chosen)
    return {"key": "quality", "value": chosen, "type": "enum"}


# --- Tier 2: profiles (machines / materials) ------------------------------

def list_machines() -> dict:
    """All configured printers + which is active.

    5.10-5.13: CuraContainerRegistry.findContainerStacks(type="machine"); each has
    getId()/getName(); active is CuraApplication.getGlobalContainerStack().
    """
    from cura.Settings.CuraContainerRegistry import CuraContainerRegistry

    active = get_application().getGlobalContainerStack()
    active_id = active.getId() if active is not None else None
    stacks = CuraContainerRegistry.getInstance().findContainerStacks(type="machine")
    machines = [
        {"id": s.getId(), "name": s.getName(), "active": s.getId() == active_id} for s in stacks
    ]
    return {"machines": machines}


def switch_machine(name: str) -> dict:
    """Activate a configured printer by id or display name.

    5.10-5.13: MachineManager.setActiveMachine(stack_id).
    """
    from cura.Settings.CuraContainerRegistry import CuraContainerRegistry

    stacks = CuraContainerRegistry.getInstance().findContainerStacks(type="machine")
    match = next((s for s in stacks if name in (s.getId(), s.getName())), None)
    if match is None:
        raise UnknownProfile(f"No printer '{name}'. Use list_machines to see the options.")
    with _suppress_profile_override_dialog():
        get_application().getMachineManager().setActiveMachine(match.getId())
    return {"id": match.getId(), "name": match.getName(), "active": True}


def _active_extruder_variant_materials():  # noqa: ANN202
    """(variant_node.materials dict, active_base_file) for the first extruder."""
    stack = get_application().getGlobalContainerStack()
    if stack is None:
        raise UnknownProfile("No active machine.")
    from cura.Machines.ContainerTree import ContainerTree

    extruder = stack.extruderList[0]
    nozzle = extruder.variant.getName()
    machine_def_id = stack.definition.getId()
    machine_node = ContainerTree.getInstance().machines[machine_def_id]
    variant_node = machine_node.variants[nozzle]
    active_material = extruder.material
    active_base = active_material.getMetaDataEntry("base_file", active_material.getId())
    return variant_node.materials, active_base


def list_materials() -> dict:
    """Materials compatible with the active machine + nozzle, with the active one.

    5.10-5.13: ContainerTree machine->variant->materials (Dict[base_file ->
    MaterialNode]); names/brands via CuraContainerRegistry metadata.
    """
    from cura.Settings.CuraContainerRegistry import CuraContainerRegistry

    materials_dict, active_base = _active_extruder_variant_materials()
    registry = CuraContainerRegistry.getInstance()

    out: list[dict] = []
    for base_file, node in materials_dict.items():
        name, brand = base_file, None
        container_id = getattr(node, "container_id", None)
        if container_id is not None:
            md = registry.findContainersMetadata(id=container_id)
            if md:
                name = md[0].get("name", base_file)
                brand = md[0].get("brand")
        out.append(
            {"id": base_file, "name": name, "brand": brand, "active": base_file == active_base}
        )
    return {"materials": out, "active": active_base}


def switch_material(name: str) -> dict:
    """Set the active extruder's material by id (base_file) or display name.

    5.10-5.13: MachineManager.setMaterialById(position, root_material_id).
    """
    from cura.Settings.CuraContainerRegistry import CuraContainerRegistry

    materials_dict, _ = _active_extruder_variant_materials()
    registry = CuraContainerRegistry.getInstance()

    target_base = None
    target_name = name
    for base_file, node in materials_dict.items():
        display = base_file
        container_id = getattr(node, "container_id", None)
        if container_id is not None:
            md = registry.findContainersMetadata(id=container_id)
            if md:
                display = md[0].get("name", base_file)
        if name in (base_file, display):
            target_base, target_name = base_file, display
            break
    if target_base is None:
        raise UnknownProfile(f"No material '{name}' for this machine. Use list_materials.")

    with _suppress_profile_override_dialog():
        ok = get_application().getMachineManager().setMaterialById("0", target_base)
    if not ok:
        raise UnknownProfile(f"Cura rejected material '{name}'.")
    return {"id": target_base, "name": target_name, "active": True}


# --- Tier 2: export G-code ------------------------------------------------

def export_gcode(path: str) -> dict:
    """Write the last successful slice's G-code to ``path``. Thread: main.

    Gated on a DONE slice AND non-empty scene.gcode_dict for the active plate, so
    we never write an empty/stale file. Path is already sandbox-validated.
    5.10-5.13: app.getMeshFileHandler().getWriterByMimeType("text/x-gcode") is the
    GCodeWriter; it writes the whole scene's gcode (ignores nodes), TextMode only.
    """
    app = get_application()
    from UM.Backend.Backend import BackendState

    scene = app.getController().getScene()
    active_bp = app.getMultiBuildPlateModel().activeBuildPlate
    gcode_dict = getattr(scene, "gcode_dict", {})
    gcode_list = gcode_dict.get(active_bp) if isinstance(gcode_dict, dict) else None

    backend = app.getBackend()
    state = getattr(backend, "_backend_state", None)
    if state != BackendState.Done or not gcode_list:
        raise ExportFailed("No completed slice to export. Run slice (reach DONE) first.")

    writer = app.getMeshFileHandler().getWriterByMimeType("text/x-gcode")
    if writer is None:
        raise ExportFailed("No G-code writer available.")

    from UM.Mesh.MeshWriter import MeshWriter

    try:
        with open(path, "w", encoding="utf-8", newline="") as stream:
            ok = writer.write(stream, None, MeshWriter.OutputMode.TextMode)
    except OSError as exc:
        raise ExportFailed(f"Could not write '{path}': {exc}") from exc
    if not ok:
        raise ExportFailed("The G-code writer failed.")

    # gcode_dict entries are multi-line chunks; count actual newlines.
    line_count = sum(str(chunk).count("\n") for chunk in gcode_list)
    return {"path": path, "lines": line_count}


# --- Tier 3 (M1): settings introspection + bulk reset --------------------

def _user_overrides(stack) -> list[dict]:  # noqa: ANN001
    """User overrides on one container stack, as ``[{key, value, type}]``.

    5.10-5.13: ``stack.userChanges`` is an InstanceContainer whose
    ``getAllKeys()`` lists exactly the keys the user (or a tool) overrode; values
    and types resolve through the owning stack (same accessors as ``get_setting``).
    """
    out: list[dict] = []
    for key in sorted(stack.userChanges.getAllKeys()):
        out.append(
            {
                "key": key,
                "value": stack.getProperty(key, "value"),
                "type": stack.getProperty(key, "type"),
            }
        )
    return out


def get_all_user_settings() -> dict:
    """Every user override currently set, split by scope.

    Returns ``{global: [...], extruders: [[...] per extruder]}`` — the only way to
    see what was changed without probing keys one by one.
    5.10-5.13: GlobalStack.userChanges + each ExtruderStack.userChanges.
    """
    stack = _global_stack()
    return {
        "global": _user_overrides(stack),
        "extruders": [_user_overrides(ex) for ex in stack.extruderList],
    }


def reset_all_settings() -> dict:
    """Remove ALL user overrides (global + every extruder); revert to baseline.

    Per-key ``removeInstance`` over a snapshot of ``getAllKeys()`` (keeps Cura's
    undo path working, unlike ``userChanges.clear()``); each removal fires the
    property-changed signal that triggers Cura's auto re-slice.
    5.10-5.13: InstanceContainer.getAllKeys() / removeInstance(key).
    """
    stack = _global_stack()

    def _drop(target) -> int:  # noqa: ANN001
        keys = list(target.userChanges.getAllKeys())
        for key in keys:
            target.userChanges.removeInstance(key)
        return len(keys)

    global_removed = _drop(stack)
    extruders_removed = [_drop(ex) for ex in stack.extruderList]
    return {
        "global_removed": global_removed,
        "extruders_removed": extruders_removed,
        "total_removed": global_removed + sum(extruders_removed),
    }


# --- Tier 3 (M1): nozzle variants ----------------------------------------

def _machine_node_and_extruder():  # noqa: ANN202
    """(machine ContainerTree node, active first extruder stack) or raise."""
    stack = get_application().getGlobalContainerStack()
    if stack is None:
        raise UnknownProfile("No active machine.")
    from cura.Machines.ContainerTree import ContainerTree

    machine_def_id = stack.definition.getId()
    machine_node = ContainerTree.getInstance().machines[machine_def_id]
    return machine_node, stack.extruderList[0]


def _active_material_base(extruder) -> str | None:  # noqa: ANN001
    """base_file id of an extruder's active material, or None."""
    material = getattr(extruder, "material", None)
    if material is None:
        return None
    return material.getMetaDataEntry("base_file", material.getId())


def list_variants() -> dict:
    """Nozzle variants compatible with the active machine, marking the active one.

    5.10-5.13: ContainerTree machines[def].variants is Dict[name -> VariantNode];
    each node carries ``container_id`` (the id) and ``variant_name`` (== the dict
    key); the active one is the first extruder's ``variant.getName()``.
    """
    machine_node, extruder = _machine_node_and_extruder()
    active_name = extruder.variant.getName()
    variants = [
        {"id": getattr(node, "container_id", name), "name": name, "active": name == active_name}
        for name, node in machine_node.variants.items()
    ]
    variants.sort(key=lambda v: v["name"])
    return {"variants": variants, "active": active_name}


def switch_variant(name: str) -> dict:
    """Set the active extruder's nozzle variant by display name or id.

    5.10-5.13: MachineManager.setVariant(position, VariantNode) — the setter also
    re-resolves material compatibility (updateMaterialWithVariant), so a nozzle
    change can swap the active material. We report whether it did.
    """
    machine_node, extruder = _machine_node_and_extruder()
    target = machine_node.variants.get(name)
    if target is None:
        target = next(
            (n for n in machine_node.variants.values() if getattr(n, "container_id", None) == name),
            None,
        )
    if target is None:
        raise UnknownProfile(f"No nozzle variant '{name}'. Use list_variants to see the options.")

    material_before = _active_material_base(extruder)
    with _suppress_profile_override_dialog():
        get_application().getMachineManager().setVariant("0", target)

    material_after = _active_material_base(extruder)
    new_name = extruder.variant.getName()
    changed = material_after != material_before
    if changed:
        note = (
            f"Active material changed to '{material_after}'; the previous "
            f"'{material_before}' is not compatible with this nozzle."
        )
    else:
        note = f"Active material '{material_after}' is still compatible with this nozzle."
    return {
        "id": getattr(target, "container_id", new_name),
        "name": new_name,
        "active": True,
        "material": material_after,
        "material_changed": changed,
        "note": note,
    }


# --- Tier 3 (M2): group / ungroup / merge --------------------------------

def _resolve_mesh_nodes(node_ids: list[str]) -> list:
    """Resolve ids to sliceable nodes; raise NodeNotFound on the first unknown id."""
    nodes: list = []
    for nid in node_ids:
        node = _find_node_by_id(nid)
        if node is None:
            raise NodeNotFound(f"No model on the plate with id '{nid}'.")
        nodes.append(node)
    return nodes


def _find_group_node_by_id(node_id: str):  # noqa: ANN202
    """The group node (GroupDecorator) whose ``_node_id`` matches, or None.

    Group nodes are not ``isSliceable`` so ``_find_node_by_id`` skips them; this
    walks the whole scene and keeps nodes whose ``isGroup`` decoration is truthy.
    """
    app = get_application()
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    for node in DepthFirstIterator(scene.getRoot()):
        if node.callDecoration("isGroup") and _node_id(node) == node_id:
            return node
    return None


def _name_group_node(group_node, base: str = "Group") -> str:  # noqa: ANN001
    """Give a freshly created group node a unique, stable id (its name).

    Group nodes are created nameless; without a name ``_node_id`` falls back to a
    volatile ``node-<addr>``. A unique "<base> (n)" makes it findable by
    ``_find_group_node_by_id`` for a later ungroup.
    """
    taken = {_node_id(n) for n in _all_sliceable_nodes()}
    app = get_application()
    from UM.Scene.Iterator.DepthFirstIterator import DepthFirstIterator

    scene = app.getController().getScene()
    taken |= {
        n.getName() for n in DepthFirstIterator(scene.getRoot()) if n.callDecoration("isGroup")
    }
    name = _unique_name(base, taken)
    group_node.setName(name)
    return name


def _build_group_node(child_nodes: list):
    """Create a decorated group node and reparent ``child_nodes`` under it.

    Replicates the essential node-building of CuraApplication.groupSelected WITHOUT
    its Selection bookkeeping or the PrintOrderManager.updatePrintOrders* call: the
    latter does ``getObjectsModel().getNodes().remove(node)``, which raises
    ``list.remove(x): x not in list`` when the ObjectsModel is momentarily stale in
    our scripted (non-event-loop-pumped) context. Building the node + a grouped
    SetParentOperation gives the same result, undoable, without that coupling.
    5.10-5.13: CuraSceneNode + GroupDecorator/ConvexHullDecorator/BuildPlateDecorator
    + cura.Operations.SetParentOperation in a UM GroupedOperation.
    """
    app = get_application()
    from cura.Operations.SetParentOperation import SetParentOperation
    from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
    from cura.Scene.ConvexHullDecorator import ConvexHullDecorator
    from cura.Scene.CuraSceneNode import CuraSceneNode
    from UM.Math.Vector import Vector
    from UM.Operations.GroupedOperation import GroupedOperation
    from UM.Scene.GroupDecorator import GroupDecorator

    scene_root = app.getController().getScene().getRoot()
    active_bp = app.getMultiBuildPlateModel().activeBuildPlate

    group_node = CuraSceneNode()
    group_node.addDecorator(GroupDecorator())
    group_node.addDecorator(ConvexHullDecorator())
    group_node.addDecorator(BuildPlateDecorator(active_bp))
    group_node.setParent(scene_root)
    group_node.setSelectable(True)

    positions = [n.getWorldPosition() for n in child_nodes]
    n = len(positions)
    center = Vector(
        sum(p.x for p in positions) / n,
        sum(p.y for p in positions) / n,
        sum(p.z for p in positions) / n,
    )
    group_node.setPosition(center)
    group_node.setCenterPosition(center)

    operation = GroupedOperation()
    for node in child_nodes:
        operation.addOperation(SetParentOperation(node, group_node))
    operation.push()
    return group_node


def _select_only(node) -> None:  # noqa: ANN001
    from UM.Scene.Selection import Selection

    Selection.clear()
    if node is not None:
        Selection.add(node)


def group_models(node_ids: list[str]) -> dict:
    """Group ≥2 models so they move as one. Returns the group id + member ids.

    The members stay ``isSliceable`` so they still appear individually in
    list_models; the returned group id is what ungroup_model consumes. (MCP
    transforms target individual members, not the group node.)
    """
    if len(node_ids) < 2:
        raise NodeNotFound("group_models needs at least 2 model ids.")
    nodes = _resolve_mesh_nodes(node_ids)
    group_node = _build_group_node(nodes)
    group_id = _name_group_node(group_node, "Group")
    members = [_node_id(c) for c in group_node.getChildren()]
    _select_only(group_node)
    return {"node_id": group_id, "members": members}


def ungroup_model(node_id: str) -> dict:
    """Ungroup a group node back into its members. Returns the freed member ids.

    Reparents each child to the group's parent via a grouped SetParentOperation
    (undoable); GroupDecorator._onChildrenChanged then drops the emptied group node
    from the scene automatically. Non-group / unknown id -> node_not_found.
    5.10-5.13: cura.Operations.SetParentOperation in a UM GroupedOperation.
    """
    group_node = _find_group_node_by_id(node_id)
    if group_node is None:
        raise NodeNotFound(f"No group with id '{node_id}' (use group_models' returned id).")
    members = [_node_id(c) for c in group_node.getChildren()]

    from cura.Operations.SetParentOperation import SetParentOperation
    from UM.Operations.GroupedOperation import GroupedOperation

    group_parent = group_node.getParent()
    children = [c for c in group_node.getChildren() if c.getParent() == group_node]
    operation = GroupedOperation()
    for child in children:
        operation.addOperation(SetParentOperation(child, group_parent))
    operation.push()
    _select_only(None)
    return {"node_id": node_id, "members": members}


def _align_merged_children(group_node) -> None:  # noqa: ANN001
    """Reset each child's transform and align them around a shared centre.

    Reimplements CuraApplication.mergeSelected's geometry: drop each child's own
    transform, then position it so all children share one origin (overlapping) —
    the dual-extrusion / multi-part alignment.
    5.10-5.13: SceneNode.getMeshData()/setTransformation()/setPosition(); MeshData
    getTransformed(Matrix())/getCenterPosition()/getZeroPosition().
    """
    from UM.Math.Matrix import Matrix
    from UM.Math.Vector import Vector

    pairs = [(c.getMeshData(), c) for c in group_node.getChildren() if c.getMeshData()]
    centers = [
        c for c in (mesh.getTransformed(Matrix()).getCenterPosition() for mesh, _ in pairs)
        if c is not None
    ]
    if centers:
        offset = Vector(
            sum(c.x for c in centers) / len(centers),
            sum(c.y for c in centers) / len(centers),
            sum(c.z for c in centers) / len(centers),
        )
    else:
        offset = Vector(0, 0, 0)
    for mesh, node in pairs:
        node.setTransformation(Matrix())
        node.setPosition(-mesh.getZeroPosition() - offset)
    bbox = group_node.getBoundingBox()
    if bbox is not None:
        group_node.setPosition(bbox.center)


def merge_models(node_ids: list[str]) -> dict:
    """Merge ≥2 meshes into one object aligned at a shared origin (dual-extrusion
    / multi-part alignment). Returns the resulting group id + member ids.
    """
    if len(node_ids) < 2:
        raise NodeNotFound("merge_models needs at least 2 model ids.")
    nodes = _resolve_mesh_nodes(node_ids)
    group_node = _build_group_node(nodes)
    _align_merged_children(group_node)
    group_id = _name_group_node(group_node, "Merged")
    members = [_node_id(c) for c in group_node.getChildren()]
    _select_only(group_node)
    return {"node_id": group_id, "members": members}


# --- Tier 3 (M3): project save / open (full workspace .3mf) ---------------

def save_project(path: str) -> dict:
    """Write the WHOLE workspace (scene + machine + material/variant + every user
    setting) to a Cura project 3MF. This is NOT a mesh-only export. Thread: main.

    5.10-5.13: app.getWorkspaceFileHandler() yields a FileHandler whose only
    writers are workspace writers; getWriter("3MFWriter") is the
    ThreeMFWorkspaceWriter. write(stream, nodes) forces BinaryMode internally and
    serialises the full workspace (the nodes supply mesh geometry). Path is already
    output-sandbox-validated.
    """
    app = get_application()
    handler = app.getWorkspaceFileHandler()
    if handler is None:
        raise ExportFailed("No workspace file handler available.")
    writer = handler.getWriter("3MFWriter")
    if writer is None:
        # Fallback: the workspace handler only holds workspace writers, so resolving
        # the 3dmanufacturing mime here returns the project (not the mesh) writer.
        writer = handler.getWriterByMimeType(
            "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
        )
    if writer is None:
        raise ExportFailed("No Cura project (workspace) writer available.")

    nodes = _all_sliceable_nodes()
    try:
        with open(path, "wb") as stream:
            ok = writer.write(stream, nodes)
    except OSError as exc:
        raise ExportFailed(f"Could not write '{path}': {exc}") from exc
    if not ok:
        raise ExportFailed("The Cura project writer failed.")
    return {"path": path, "models": len(nodes)}


class _HeadlessWorkspaceDialog:
    """Inert stand-in for the project-open WorkspaceDialog.

    ThreeMFWorkspaceReader.preRead normally configures + shows this modal (to
    resolve machine/material conflicts) and BLOCKS on ``waitForClose()``; over the
    HTTP bridge that hangs. Swapping it in lets preRead run its real archive parse
    — which populates ``_machine_info`` that read() needs — while the dialog part is
    a no-op: setters do nothing, it never blocks, and ``getResult()`` returns a
    non-empty "create new" result so preRead returns ``accepted`` (and skips the
    None-fill loop, since the values are non-None).
    5.10-5.13: resolve_strategy_keys == [machine, material, quality_changes].
    """

    class _NoopModel:
        count = 0

        def clear(self) -> None: ...

        def addSettingsFromStack(self, *a: object, **k: object) -> None: ...

    def __init__(self) -> None:
        self.exportedSettingModel = self._NoopModel()
        self.updatableMachinesModel = self._NoopModel()
        # Properties read (not called) by the reader: missingPackages is ITERATED
        # (reader line ~1371), so it must be an empty iterable, not a stub callable.
        self.missingPackages: list = []
        self.currentMachinePositionIndex = 0

    def __getattr__(self, _name: str):  # noqa: ANN204 - any other call is an inert setter
        return lambda *a, **k: None

    def getResult(self) -> dict:
        return {"machine": "new", "material": "new", "quality_changes": "new"}

    def waitForClose(self) -> None:
        return None


def _count_project_models(path: str) -> int | None:
    """Number of objects a project .3mf places on the plate, read from the FILE.

    The scene/node count is unreliable right after an open: Cura 5.13's reader
    returns an EMPTY node list from read() and loads the meshes on a later
    ``callLater`` tick (deferred), so nothing is in the scene yet when the open
    returns; 5.10 returns the nodes inline. The .3mf is the synchronous,
    version-independent source of truth — count ``<build>/<item>`` in the 3MF core
    model part. Returns None if it can't be parsed (caller falls back).
    Stdlib only (zipfile + ElementTree), so it is safe in Cura's interpreter.
    """
    import xml.etree.ElementTree as ET
    import zipfile

    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]

    try:
        with zipfile.ZipFile(path) as zf:
            model_part = next(
                (n for n in zf.namelist() if n.lower().endswith("3dmodel.model")), None
            )
            if model_part is None:
                return None
            root = ET.fromstring(zf.read(model_part))
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return None

    for element in root.iter():
        if _local(element.tag) == "build":
            return sum(1 for child in element if _local(child.tag) == "item")
    return 0


def open_project_workspace(path: str, mode: str = "create_new") -> dict:
    """Open a Cura project 3MF as a PROJECT, with NO dialog, SYNCHRONOUSLY. Main.

    Returns ``{name, models}`` (the workspace name + count of model nodes added).

    The normal entry point (readLocalFile open_as_project → WorkspaceFileHandler →
    ReadFileJob) shows the interactive WorkspaceDialog and runs async; over the HTTP
    bridge that modal hangs. We instead drive the reader directly with its dialog
    swapped for an inert stand-in (``_HeadlessWorkspaceDialog``): preRead's real
    parse still populates ``_machine_info`` (which read() needs), but nothing blocks.
    The read is synchronous, so no signal handshake is needed; we then apply the
    result exactly as WorkspaceFileHandler._readWorkspaceFinished does.

    NOTE: with the dialog inert (no populated updatable-machines model), read() takes
    the "create new machine" path — opening creates a FRESH machine instance from the
    project (settings/material/scene survive) rather than updating the active machine
    in place. Path is load-sandbox-validated.
    5.10-5.13: getReaderForFile → ThreeMFWorkspaceReader; preRead → read() ->
    (nodes, metadata); then resetWorkspace + AddSceneNodeOperation per node.

    ``mode``:
      - "create_new" (VERIFIED on 5.10 + 5.13): the path below — forces the reader's
        resolve strategies to "new" so the open builds a fresh machine.
      - "replace_active" (# VERIFY: NOT verified — fail-closed): would instead set the
        resolve strategies to "override" and target the ACTIVE machine so the project
        overwrites it in place (no new machine, no undo). That re-enters the reader's
        updatableMachinesModel / override branch this create_new path deliberately
        avoids, so it MUST be read from installed 5.10 + 5.13 source and live-smoked
        before being enabled. Until then it raises rather than guess on the
        destructive path.
    """
    if mode == "replace_active":
        # VERIFY: in-place override open. The override branch of
        # ThreeMFWorkspaceReader.read() (5.10 ~L806 / 5.13 ~L799) is taken only when
        # BOTH `_resolve_strategies["machine"] == "override"` AND
        # `_dialog.updatableMachinesModel.count > 0`; it then resolves the target via
        # `_dialog.getMachineToOverride()` and applies the project to that EXISTING
        # GlobalStack. Enabling it would mean: (a) a stub whose updatableMachinesModel
        # reports count>0 and getMachineToOverride() returns the ACTIVE machine id,
        # (b) `_resolve_strategies = {k: "override"}`, and (c) a hard guard that the
        # active machine's definition == `_machine_info.definition_id`.
        # STAYS FAIL-CLOSED because it is destructive with NO undo and mutates the
        # global container registry beyond the active stack — the material-override
        # path `removeContainer(root_material_id)` (5.10 ~L888 / 5.13 ~L879) deletes
        # and re-deserialises material containers. A single live round-trip cannot
        # prove the edge cases (extruder-count / quality_changes / material removal)
        # safe, so this must not be enabled by guessing. Use mode=create_new.
        raise LoadFailed(
            "mode=replace_active is not enabled in this build (pending Cura-source "
            "verification of the in-place override path). Use mode=create_new."
        )
    if mode != "create_new":
        raise LoadFailed(f"Unknown mode '{mode}'. Use create_new or replace_active.")
    app = get_application()
    from UM.Workspace.WorkspaceReader import WorkspaceReader

    handler = app.getWorkspaceFileHandler()
    if handler is None:
        raise LoadFailed("No workspace file handler available.")
    reader = handler.getReaderForFile(path)
    if reader is None:
        raise LoadFailed(f"No workspace reader can open '{path}'.")

    # setloadingWorkspace is a 5.13+ flag (helps suppress the discard dialog); it
    # does not exist on 5.10, and we already neutralise the dialogs ourselves, so
    # treat it as optional.
    set_loading = getattr(app, "setloadingWorkspace", None)
    real_dialog = getattr(reader, "_dialog", None)
    try:
        if callable(set_loading):
            set_loading(True)
        if real_dialog is not None:
            reader._dialog = _HeadlessWorkspaceDialog()  # type: ignore[assignment]
        pre = reader.preRead(path, show_dialog=True)
        if pre != WorkspaceReader.PreReadResult.accepted:
            raise LoadFailed(
                f"'{path}' is not a readable Cura project (use load_model for a mesh 3MF)."
            )
        strategies = getattr(reader, "_resolve_strategies", None)
        if isinstance(strategies, dict):
            reader._resolve_strategies = {key: "new" for key in strategies}
        result = reader.read(path)
    finally:
        if real_dialog is not None:
            reader._dialog = real_dialog
        if callable(set_loading):
            set_loading(False)

    nodes, metadata = result if isinstance(result, tuple) else (result, {})
    if nodes is None:
        raise LoadFailed("The project loaded no scene.")

    from UM.Operations.AddSceneNodeOperation import AddSceneNodeOperation

    app.resetWorkspace()
    root = app.getController().getScene().getRoot()
    for node in nodes:
        AddSceneNodeOperation(node, root).push()
    try:
        app.getWorkspaceMetadataStorage().setAllData(metadata)
    except Exception:  # noqa: BLE001 - metadata is non-essential to the open
        pass
    # Count models from the .3mf itself, not the scene: on 5.13 read() returns no
    # nodes (deferred callLater load), so a scene/node count reads 0 here even though
    # list_models shows them a tick later. The file count is correct on both versions;
    # fall back to the (inline) node count only if the file can't be parsed.
    models = _count_project_models(path)
    if models is None:
        models = sum(
            1 for node in nodes if node.getMeshData() is not None or node.callDecoration("isGroup")
        )
    name = reader.workspaceName() or path
    return {
        "name": name,
        "models": models,
        "note": f"Opened '{name}' as a new printer; the previous workspace was replaced.",
    }


def preview_project_workspace(path: str) -> dict:
    """Validate a Cura project 3MF WITHOUT mutating the workspace. Thread: main.

    Runs ONLY ThreeMFWorkspaceReader.preRead — which parses the archive (populating
    the reader's _machine_info) but does NOT touch the scene or the container
    registry — with the interactive dialog swapped for the inert stand-in so nothing
    blocks. Returns {valid_project, name}. Backs open_project's confirm=false preview.
    5.10-5.13: getReaderForFile → preRead(show_dialog=True) with _dialog neutralised;
    no read()/resetWorkspace, so the current workspace is untouched.
    """
    app = get_application()
    from UM.Workspace.WorkspaceReader import WorkspaceReader

    handler = app.getWorkspaceFileHandler()
    if handler is None:
        raise LoadFailed("No workspace file handler available.")
    reader = handler.getReaderForFile(path)
    if reader is None:
        raise LoadFailed(f"No workspace reader can open '{path}'.")

    real_dialog = getattr(reader, "_dialog", None)
    try:
        if real_dialog is not None:
            reader._dialog = _HeadlessWorkspaceDialog()  # type: ignore[assignment]
        pre = reader.preRead(path, show_dialog=True)
    finally:
        if real_dialog is not None:
            reader._dialog = real_dialog
    if pre != WorkspaceReader.PreReadResult.accepted:
        raise LoadFailed(
            f"'{path}' is not a readable Cura project (use load_model for a mesh 3MF)."
        )
    try:
        name = reader.workspaceName()
    except Exception:  # noqa: BLE001 - name is informational
        name = None
    return {"valid_project": True, "name": name or path}


def workspace_summary() -> dict:
    """{machine, models} snapshot for open_project's before/after report. Main."""
    stack = get_application().getGlobalContainerStack()
    machine = stack.getName() if stack is not None else None
    return {"machine": machine, "models": count_sliceable_nodes()}


# --- Tier 3 (M4): per-object settings & mesh types -----------------------

# The four mutually-exclusive mesh-role booleans on the per-object stack. At most
# one is ever true; "normal" means none of them. Order mirrors Cura's
# PerObjectSettingsTool so getMeshType resolves identically.
_MESH_KEYS = ["infill_mesh", "cutting_mesh", "support_mesh", "anti_overhang_mesh"]
_MESH_TYPES = {"normal", "support_mesh", "anti_overhang_mesh", "infill_mesh", "cutting_mesh"}

# Auto-settings Cura layers onto an infill (modifier) mesh so it adds no skin/walls
# by default; removed again when the mesh stops being an infill mesh. Verbatim from
# PerObjectSettingsTool.setMeshType (5.10 == 5.13).
_INFILL_MESH_SPECIALIZED = {
    "top_bottom_thickness": 0,
    "top_thickness": "=top_bottom_thickness",
    "bottom_thickness": "=top_bottom_thickness",
    "top_layers": "=0 if infill_sparse_density == 100 else math.ceil(round(top_thickness / resolveOrValue('layer_height'), 4))",  # noqa: E501
    "bottom_layers": "=0 if infill_sparse_density == 100 else math.ceil(round(bottom_thickness / resolveOrValue('layer_height'), 4))",  # noqa: E501
    "wall_thickness": 0,
    "wall_line_count": "=max(1, round((wall_thickness - wall_line_width_0) / wall_line_width_x) + 1) if wall_thickness != 0 else 0",  # noqa: E501
}


def _json_safe(value):  # noqa: ANN001, ANN202
    """Coerce a setting value to something json.dumps can serialise.

    Resolved per-object values are normally scalars, but a stray SettingFunction or
    other Cura object would crash the HTTP response encoder; stringify those.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return str(value)


def _require_mesh_node(node_id: str):  # noqa: ANN202
    node = _find_node_by_id(node_id)
    if node is None:
        raise NodeNotFound(f"No model on the plate with id '{node_id}'.")
    return node


def _ensure_override_stack(node):  # noqa: ANN001, ANN202
    """The node's per-object settings stack, adding the decorator if absent.

    5.10-5.13: node.callDecoration("getStack") -> PerObjectContainerStack (None
    until a SettingOverrideDecorator is added). Mirrors PerObjectSettingsTool.
    """
    stack = node.callDecoration("getStack")
    if not stack:
        from cura.Settings.SettingOverrideDecorator import SettingOverrideDecorator

        node.addDecorator(SettingOverrideDecorator())
        stack = node.callDecoration("getStack")
    return stack


def _current_mesh_type(stack) -> str:  # noqa: ANN001
    """Resolved mesh role on a per-object stack ("normal" if none set)."""
    if not stack:
        return "normal"
    settings = stack.getTop()
    for key in _MESH_KEYS:
        if settings.getInstance(key) and settings.getProperty(key, "value"):
            return key
    return "normal"


def set_model_setting(node_id: str, key: str, value) -> dict:  # noqa: ANN001
    """Apply a per-object override to ONE model's per-object stack (not global).

    Validation is identical to the global set_setting (key exists, type coercion,
    min/max, enum options); only the target differs — the value lands on the node's
    own settings container, so it overrides just this model. Auto re-slices.
    5.10-5.13: node per-object stack getTop() InstanceContainer + SettingInstance.
    """
    node = _require_mesh_node(node_id)
    global_stack = _global_stack()
    if not _setting_exists(global_stack, key):
        raise UnknownSetting(f"Unknown setting '{key}'.")

    setting_type = global_stack.getProperty(key, "type")
    coerced = _coerce_value(setting_type, value)
    if isinstance(coerced, (int, float)) and not isinstance(coerced, bool):
        minimum = global_stack.getProperty(key, "minimum_value")
        maximum = global_stack.getProperty(key, "maximum_value")
        if minimum is not None and coerced < float(minimum):
            raise InvalidSettingValue(f"{key}={coerced} is below the minimum {minimum}.")
        if maximum is not None and coerced > float(maximum):
            raise InvalidSettingValue(f"{key}={coerced} is above the maximum {maximum}.")
    options = global_stack.getProperty(key, "options")
    if options and coerced not in options:
        raise InvalidSettingValue(
            f"{key}={coerced!r} is not a valid option. Allowed: {sorted(options)}."
        )

    stack = _ensure_override_stack(node)
    settings = stack.getTop()
    from UM.Settings.SettingInstance import SettingInstance

    instance = settings.getInstance(key)
    if instance is None:
        definition = stack.getSettingDefinition(key)
        instance = SettingInstance(definition, settings)
        settings.addInstance(instance)
    instance.setProperty("value", coerced)
    return {
        "node_id": node_id,
        "key": key,
        "value": _json_safe(stack.getProperty(key, "value")),
        "type": setting_type,
    }


def reset_model_setting(node_id: str, key: str) -> dict:
    """Remove one per-object override from a model (no-op if it wasn't set).

    5.10-5.13: per-object stack getTop().removeInstance(key).
    """
    node = _require_mesh_node(node_id)
    if not _setting_exists(_global_stack(), key):
        raise UnknownSetting(f"Unknown setting '{key}'.")
    stack = node.callDecoration("getStack")
    removed = False
    if stack:
        settings = stack.getTop()
        if settings.getInstance(key):
            settings.removeInstance(key)
            removed = True
    return {"node_id": node_id, "key": key, "removed": removed}


def set_mesh_type(node_id: str, mesh_type: str) -> dict:
    """Set a model's mesh role; "normal" clears it. Replicates Cura's
    PerObjectSettingsTool.setMeshType (minus the UI visibility handler).

    The four roles are mutually-exclusive booleans on the per-object stack; this
    adds the chosen one and removes the others, and layers/removes the infill-mesh
    skin/wall auto-settings exactly as Cura does. Auto re-slices.
    5.10-5.13: stack.getTop() add/removeInstance + SettingInstance.
    """
    if mesh_type not in _MESH_TYPES:
        raise InvalidSettingValue(
            f"Invalid mesh type '{mesh_type}'. Allowed: {sorted(_MESH_TYPES)}."
        )
    node = _require_mesh_node(node_id)
    target = "" if mesh_type == "normal" else mesh_type

    stack = node.callDecoration("getStack")
    old_mesh_type = _current_mesh_type(stack)
    old_target = "" if old_mesh_type == "normal" else old_mesh_type
    if old_target == target:
        return {"node_id": node_id, "mesh_type": mesh_type, "changed": False}

    stack = _ensure_override_stack(node)
    settings = stack.getTop()
    from UM.Settings.SettingInstance import SettingInstance

    for key in _MESH_KEYS:
        if key != target:
            if settings.getInstance(key):
                settings.removeInstance(key)
        elif not (settings.getInstance(key) and settings.getProperty(key, "value")):
            definition = stack.getSettingDefinition(key)
            new_instance = SettingInstance(definition, settings)
            new_instance.setProperty("value", True)
            new_instance.resetState()  # not a user state, mirroring Cura
            settings.addInstance(new_instance)

    # Infill mesh gets skin/wall-suppressing auto-settings; remove them on the way out.
    for key, expr in _INFILL_MESH_SPECIALIZED.items():
        if target == "infill_mesh":
            if settings.getInstance(key) is None:
                definition = stack.getSettingDefinition(key)
                new_instance = SettingInstance(definition, settings)
                new_instance.setProperty("value", expr)
                new_instance.resetState()
                settings.addInstance(new_instance)
        elif old_target == "infill_mesh" and settings.getInstance(key):
            settings.removeInstance(key)

    return {"node_id": node_id, "mesh_type": mesh_type, "changed": True}


def get_model_settings(node_id: str) -> dict:
    """A model's per-object overrides + its current mesh type.

    Returns {node_id, mesh_type, settings:[{key, value}]}. The mesh-role booleans
    are reported via ``mesh_type`` (not duplicated in ``settings``).
    5.10-5.13: per-object stack getTop().getAllKeys()/getProperty.
    """
    node = _require_mesh_node(node_id)
    stack = node.callDecoration("getStack")
    mesh_type = _current_mesh_type(stack)
    overrides: list[dict] = []
    if stack:
        settings = stack.getTop()
        for key in sorted(settings.getAllKeys()):
            if key in _MESH_KEYS:
                continue
            # Read the RESOLVED value through the stack, not the raw instance: a
            # per-object instance can hold a SettingFunction (e.g. the infill-mesh
            # auto-settings like top_thickness="=top_bottom_thickness"), which is not
            # JSON-serialisable. The stack evaluates it to a concrete scalar.
            overrides.append({"key": key, "value": _json_safe(stack.getProperty(key, "value"))})
    return {"node_id": node_id, "mesh_type": mesh_type, "settings": overrides}


def get_plugin_version() -> str:
    return "0.1.0"
