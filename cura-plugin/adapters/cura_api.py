"""The anti-corruption layer: the ONLY module that touches Cura/Uranium internals.

Everything else in the plugin calls these functions. When a Cura version renames
or moves an internal, this is the single file to fix.

STATUS: VERIFIED against UltiMaker Cura 5.10.0 AND 5.13.0 source (the bundled
``cura/`` + ``UM/`` packages and the ``CuraEngineBackend`` plugin). Every accessor
below was read from that source; the previous best-effort ``# VERIFY:`` guesses
have been replaced with the confirmed calls. The full happy path + security smoke
test is green on both versions with this file UNCHANGED (Cura SDK 8 on 5.10.0,
8.12.0 on 5.13.0 — same major, identical internals here). Where a behaviour is an
intentional approximation (only ``_fits_build_volume``'s fallback path) it is
noted inline.

All functions here assume they are called on Cura's MAIN THREAD (callers route
through ``bridge.main_thread.run_on_main_thread``), except pure-data reads noted
as thread-agnostic. The load + slice handshakes split work between a main-thread
trigger and a worker-thread wait (see operations/load.py, operations/slice.py).
"""
from __future__ import annotations

import enum
import math
from typing import Callable

from ..errors import (
    ExportFailed,
    InvalidSettingValue,
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


def get_plugin_version() -> str:
    return "0.1.0"
