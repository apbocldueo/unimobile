export type CanvasPoint = { x: number; y: number };
export type CanvasRect = CanvasPoint & { width: number; height: number };

/** Check finite positive geometry before interpreting it as a visible area. */
function usable(rect: CanvasRect): boolean {
  return Object.values(rect).every(Number.isFinite) && rect.width > 0 && rect.height > 0;
}

/** Test padded intersection without changing existing node positions. */
function overlaps(left: CanvasRect, right: CanvasRect): boolean {
  return left.x < right.x + right.width + 20 && left.x + left.width + 20 > right.x
    && left.y < right.y + right.height + 20 && left.y + left.height + 20 > right.y;
}

/** Choose a bounded, visible placement from flow-space geometry.
 * Args: visible is the unobscured viewport in flow coordinates; size is the new
 * node estimate; occupied contains current measured or estimated node boxes.
 * Returns: A finite location, or null while the canvas cannot be measured.
 * Narrow viewports retain the node's upper-left interaction area; callers expose
 * an explicit enlarge/reveal control instead of claiming the whole card fits.
 */
export function visiblePlacement(
  visible: CanvasRect,
  size: { width: number; height: number },
  occupied: CanvasRect[],
): CanvasPoint | null {
  if (!usable(visible) || !usable({ x: 0, y: 0, ...size })) return null;
  const maxX = visible.x + Math.max(0, visible.width - size.width);
  const maxY = visible.y + Math.max(0, visible.height - size.height);
  /** Snap within the usable region, including non-grid-aligned viewport edges. */
  const point = (x: number, y: number): CanvasPoint => ({
    x: Math.min(maxX, Math.max(visible.x, Math.round(x / 20) * 20)),
    y: Math.min(maxY, Math.max(visible.y, Math.round(y / 20) * 20)),
  });
  const center = point((visible.x + maxX) / 2, (visible.y + maxY) / 2);
  const candidates = [center];
  // A fixed 9×9 search remains bounded even on extreme zoom or large graphs.
  for (let row = 0; row < 9; row += 1) {
    for (let column = 0; column < 9; column += 1) {
      candidates.push(point(visible.x + (maxX - visible.x) * column / 8, visible.y + (maxY - visible.y) * row / 8));
    }
  }
  const boxes = occupied.filter(usable);
  return candidates.find((candidate) => !boxes.some((box) => overlaps({ ...candidate, ...size }, box))) ?? center;
}
