"""FamilyTree — Friend edges + parent→child edges.

Edges:
  · friend(a, b)        — symmetric; both workers reference each other
  · parent_of(a, b)     — a is parent of b; b's parent_id = a
  · sibling(b1, b2)     — derived; siblings share a parent

Constraints:
  · MAX_CHILDREN_PER_PARENT = 3
  · A worker may have many friends (no cap currently, but Reflection
    will warn if a single worker accrues > 10 friends — likely a graph
    bug).
  · Friend edges have timestamps.
  · Child edges have a status: pending_birth (kernel proposed, signatures
    pending) → confirmed_birth (both signatures + worker created) →
    growing (under classroom) → independent (own certifications,
    earning).

The actual NEW worker entity (when a child is born) is created by a
SEPARATE Claude phase that writes to the workforce registry. This module
only tracks the cognitive-side lineage — it never touches the workforce
file directly.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple, Any
import time

from . import write_registry, append_log, now


MAX_CHILDREN_PER_PARENT = 3


@dataclass
class FriendEdge:
    a: str
    b: str
    grant_id: str
    granted_ts: float
    note: str = ""


@dataclass
class ChildEdge:
    parent_id: str
    child_id: str
    grant_id: str
    granted_ts: float
    status: str = "pending_birth"     # pending_birth | confirmed_birth | growing | independent | retired
    inherited_gene: Optional[Dict[str, Any]] = None
    note: str = ""


class FamilyTree:
    def __init__(self):
        self._friends: Dict[str, FriendEdge] = {}    # edge_id → edge
        self._friends_by_worker: Dict[str, Set[str]] = {}   # worker → set of friend worker ids
        self._children: Dict[str, ChildEdge] = {}    # edge_id → edge
        self._children_by_parent: Dict[str, List[str]] = {}    # parent_id → [child_id, …]
        self._parent_by_child: Dict[str, str] = {}     # child_id → parent_id

    # ── friends ───────────────────────────────────────────────────
    def add_friend_edge(self, a: str, b: str, grant_id: str,
                          note: str = "") -> Optional[FriendEdge]:
        if a == b:
            return None
        edge_id = f"friend:{a}:{b}:{int(time.time()*1000)}"
        e = FriendEdge(a=a, b=b, grant_id=grant_id,
                        granted_ts=time.time(), note=note)
        self._friends[edge_id] = e
        self._friends_by_worker.setdefault(a, set()).add(b)
        self._friends_by_worker.setdefault(b, set()).add(a)
        append_log("family_tree.jsonl", {
            "event": "friend_added", "edge_id": edge_id,
            "a": a, "b": b, "grant_id": grant_id,
        })
        return e

    def friends_of(self, worker_id: str) -> List[str]:
        return sorted(self._friends_by_worker.get(worker_id, set()))

    # ── children ──────────────────────────────────────────────────
    def add_child_edge(self, parent_id: str, child_id: str,
                         grant_id: str,
                         inherited_gene: Optional[Dict[str, Any]] = None,
                         note: str = "") -> Optional[ChildEdge]:
        # Cap check
        existing = self._children_by_parent.get(parent_id, [])
        if len(existing) >= MAX_CHILDREN_PER_PARENT:
            append_log("family_tree.jsonl", {
                "event": "child_refused_at_cap",
                "parent_id": parent_id, "would_be": child_id,
                "existing_count": len(existing),
                "cap": MAX_CHILDREN_PER_PARENT,
            })
            return None
        if child_id in self._parent_by_child:
            append_log("family_tree.jsonl", {
                "event": "child_refused_already_has_parent",
                "child_id": child_id,
                "existing_parent": self._parent_by_child[child_id],
                "would_be_parent": parent_id,
            })
            return None
        edge_id = f"child:{parent_id}:{child_id}:{int(time.time()*1000)}"
        e = ChildEdge(parent_id=parent_id, child_id=child_id,
                       grant_id=grant_id, granted_ts=time.time(),
                       inherited_gene=inherited_gene, note=note)
        self._children[edge_id] = e
        self._children_by_parent.setdefault(parent_id, []).append(child_id)
        self._parent_by_child[child_id] = parent_id
        append_log("family_tree.jsonl", {
            "event": "child_added", "edge_id": edge_id,
            "parent_id": parent_id, "child_id": child_id,
            "grant_id": grant_id,
            "inherited_gene": inherited_gene,
        })
        return e

    def mark_child_status(self, child_id: str, new_status: str,
                            note: str = "") -> bool:
        # find the edge for this child
        for e in self._children.values():
            if e.child_id == child_id:
                e.status = new_status
                if note:
                    e.note = (e.note + "; " if e.note else "") + note
                append_log("family_tree.jsonl", {
                    "event": "child_status_change",
                    "child_id": child_id, "new_status": new_status,
                    "note": note,
                })
                return True
        return False

    def children_of(self, parent_id: str) -> List[str]:
        return list(self._children_by_parent.get(parent_id, []))

    def parent_of(self, child_id: str) -> Optional[str]:
        return self._parent_by_child.get(child_id)

    def lineage_of(self, worker_id: str) -> List[str]:
        """Return ancestor ids ordered oldest → most recent."""
        chain = []
        cur = self.parent_of(worker_id)
        while cur is not None:
            chain.insert(0, cur)
            cur = self.parent_of(cur)
        return chain

    def descendants_of(self, worker_id: str) -> List[str]:
        out = []
        stack = list(self.children_of(worker_id))
        while stack:
            cid = stack.pop()
            out.append(cid)
            stack.extend(self.children_of(cid))
        return out

    def children_count(self, parent_id: str) -> int:
        return len(self._children_by_parent.get(parent_id, []))

    def is_at_child_cap(self, parent_id: str) -> bool:
        return self.children_count(parent_id) >= MAX_CHILDREN_PER_PARENT

    # ── snapshot ──────────────────────────────────────────────────
    def snapshot(self) -> Dict[str, Any]:
        friend_rows = [asdict(e) for e in self._friends.values()]
        child_rows = [asdict(e) for e in self._children.values()]
        # Generation depth per child
        generation = {}
        for e in self._children.values():
            depth = len(self.lineage_of(e.child_id))
            generation[e.child_id] = depth
        gen_counts: Dict[int, int] = {}
        for d in generation.values():
            gen_counts[d] = gen_counts.get(d, 0) + 1
        return {
            "ok": True,
            "kind": "cognitive_family_tree",
            "generated_ts": now(),
            "policy": ("Kernel writes lineage edges. Actual worker spawn "
                        "happens in a separate Claude phase that writes "
                        "the workforce registry; until then, child status "
                        "stays 'pending_birth'."),
            "max_children_per_parent": MAX_CHILDREN_PER_PARENT,
            "friend_edge_count": len(self._friends),
            "child_edge_count": len(self._children),
            "generation_counts": gen_counts,
            "parents_with_max_children": sorted([
                p for p, kids in self._children_by_parent.items()
                if len(kids) >= MAX_CHILDREN_PER_PARENT
            ]),
            "friends_sample": friend_rows[:60],
            "children_sample": child_rows[:60],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_family_tree.json", snap)
        return snap

    def load_from_snapshot(self) -> int:
        """Rehydrate friend + child edges from the persisted registry."""
        from . import COG_REG, load
        d = load(COG_REG / "cognitive_family_tree.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("friends_sample") or []:
            a, b = r.get("a"), r.get("b")
            if not (a and b):
                continue
            edge_id = f"friend:{a}:{b}:{int((r.get('granted_ts') or 0)*1000)}"
            if edge_id in self._friends:
                continue
            e = FriendEdge(a=a, b=b,
                            grant_id=r.get("grant_id", ""),
                            granted_ts=float(r.get("granted_ts") or 0),
                            note=r.get("note", ""))
            self._friends[edge_id] = e
            self._friends_by_worker.setdefault(a, set()).add(b)
            self._friends_by_worker.setdefault(b, set()).add(a)
            count += 1
        for r in d.get("children_sample") or []:
            pid, cid = r.get("parent_id"), r.get("child_id")
            if not (pid and cid):
                continue
            edge_id = f"child:{pid}:{cid}:{int((r.get('granted_ts') or 0)*1000)}"
            if edge_id in self._children:
                continue
            e = ChildEdge(parent_id=pid, child_id=cid,
                           grant_id=r.get("grant_id", ""),
                           granted_ts=float(r.get("granted_ts") or 0),
                           status=r.get("status", "pending_birth"),
                           inherited_gene=r.get("inherited_gene"),
                           note=r.get("note", ""))
            self._children[edge_id] = e
            self._children_by_parent.setdefault(pid, []).append(cid)
            self._parent_by_child[cid] = pid
            count += 1
        return count


_TREE: Optional[FamilyTree] = None


def family_tree() -> FamilyTree:
    global _TREE
    if _TREE is None:
        _TREE = FamilyTree()
    return _TREE
