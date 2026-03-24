/**
 * A* Pathfinding for OptiSlot Parking Graph
 * Pure JavaScript – no external dependencies.
 *
 * Handles multi-floor transitions via "transition" nodes.
 * Uses Euclidean distance as the heuristic, with floor
 * difference factored in through neighbour edge weights.
 */

/**
 * Euclidean heuristic between two nodes.
 * Floor is intentionally ignored here because the actual
 * cross-floor cost is already encoded in edge weights.
 */
function heuristic(a, b) {
    const dx = a.x - b.x;
    const dy = a.y - b.y;
    return Math.sqrt(dx * dx + dy * dy);
}

/**
 * Runs the A* algorithm on the parking node graph.
 *
 * @param {Object} nodes  – The `nodes` object from parkingGraph.json
 * @param {string} startId – ID of the start node
 * @param {string} endId   – ID of the goal node
 * @returns {{ path: string[], cost: number, floors: number[] }}
 *   path  – ordered list of node IDs from start to end
 *   cost  – total weighted cost
 *   floors – unique floors traversed in order of appearance
 */
export function findPath(nodes, startId, endId) {
    if (!nodes[startId] || !nodes[endId]) {
        return { path: [], cost: Infinity, floors: [] };
    }

    if (startId === endId) {
        return { path: [startId], cost: 0, floors: [nodes[startId].floor] };
    }

    const openSet = new Set([startId]);
    const cameFrom = {};
    const gScore = {};
    const fScore = {};

    // Initialise scores
    for (const id of Object.keys(nodes)) {
        gScore[id] = Infinity;
        fScore[id] = Infinity;
    }
    gScore[startId] = 0;
    fScore[startId] = heuristic(nodes[startId], nodes[endId]);

    while (openSet.size > 0) {
        // Pick node in openSet with the lowest fScore
        let current = null;
        let currentF = Infinity;
        for (const id of openSet) {
            if (fScore[id] < currentF) {
                currentF = fScore[id];
                current = id;
            }
        }

        if (current === endId) {
            return reconstructPath(nodes, cameFrom, current, gScore[current]);
        }

        openSet.delete(current);

        const currentNode = nodes[current];
        if (!currentNode.neighbors) continue;

        for (const [neighborId, weight] of Object.entries(currentNode.neighbors)) {
            if (!nodes[neighborId]) continue; // safety

            const tentativeG = gScore[current] + weight;

            if (tentativeG < gScore[neighborId]) {
                cameFrom[neighborId] = current;
                gScore[neighborId] = tentativeG;
                fScore[neighborId] = tentativeG + heuristic(nodes[neighborId], nodes[endId]);

                if (!openSet.has(neighborId)) {
                    openSet.add(neighborId);
                }
            }
        }
    }

    // No path found
    return { path: [], cost: Infinity, floors: [] };
}

/**
 * Reconstruct the path and collect floor information.
 */
function reconstructPath(nodes, cameFrom, current, totalCost) {
    const path = [current];

    while (cameFrom[current] !== undefined) {
        current = cameFrom[current];
        path.unshift(current);
    }

    // Collect unique floors in traversal order
    const floors = [];
    for (const id of path) {
        const floor = nodes[id].floor;
        if (floors.length === 0 || floors[floors.length - 1] !== floor) {
            floors.push(floor);
        }
    }

    return { path, cost: totalCost, floors };
}

/**
 * Split a full path into per-floor segments.
 * Each segment is { floor, nodes: string[], transitionLabel?: string }
 *
 * @param {Object} nodesData – The full nodes object
 * @param {string[]} path     – Ordered node IDs from findPath
 * @returns {Array<{ floor: number, nodes: string[], transitionLabel?: string }>}
 */
export function splitPathByFloor(nodesData, path) {
    if (!path || path.length === 0) return [];

    const segments = [];
    let currentFloor = nodesData[path[0]].floor;
    let currentSegment = { floor: currentFloor, nodes: [] };

    for (const nodeId of path) {
        const node = nodesData[nodeId];

        if (node.floor !== currentFloor) {
            // Find the transition node (last node of previous segment)
            const lastNodeId = currentSegment.nodes[currentSegment.nodes.length - 1];
            const lastNode = nodesData[lastNodeId];
            currentSegment.transitionLabel = lastNode.label;
            segments.push(currentSegment);

            currentFloor = node.floor;
            currentSegment = { floor: currentFloor, nodes: [] };
        }

        currentSegment.nodes.push(nodeId);
    }

    // Push last segment
    if (currentSegment.nodes.length > 0) {
        segments.push(currentSegment);
    }

    return segments;
}

/**
 * Get floor display name.
 */
export function getFloorLabel(floor) {
    if (floor === 0) return 'Ground Floor';
    if (floor < 0) return `Basement ${Math.abs(floor)}`;
    return `Floor ${floor}`;
}
