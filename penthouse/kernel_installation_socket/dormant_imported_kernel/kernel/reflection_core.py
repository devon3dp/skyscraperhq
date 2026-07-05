from datetime import datetime, UTC

class ReflectionCore:
    def __init__(self, memory, departments, missions, lifts, graph, beliefs, semantic):
        self.memory = memory
        self.departments = departments
        self.missions = missions
        self.lifts = lifts
        self.graph = graph
        self.beliefs = beliefs
        self.semantic = semantic

    def now(self):
        return datetime.now(UTC).isoformat()

    def reflect(self):
        memory_summary = self.memory.summary()
        dept_summary = self.departments.dashboard()
        mission_summary = self.missions.dashboard()
        lift_summary = self.lifts.dashboard()

        lessons = []

        lessons.append(f"Memory contains {memory_summary.get('events', 0)} events and {memory_summary.get('facts', 0)} facts.")
        lessons.append(f"Department floor contains {dept_summary.get('department_count', 0)} departments with average health {dept_summary.get('average_health', 0)}.")
        lessons.append(f"Mission floor contains {mission_summary.get('active_missions', 0)} active missions.")
        lessons.append(f"Lift system has recorded {lift_summary.get('total_lift_events', 0)} internal events.")

        if memory_summary.get("events", 0) > 0:
            self.beliefs.assert_belief("QSB is accumulating persistent operational memory.", 0.5, "reflection over memory events")

        if dept_summary.get("department_count", 0) >= 5:
            self.beliefs.assert_belief("QSB skyscraper departments are structurally online.", 0.5, "reflection over department dashboard")

        if lift_summary.get("total_lift_events", 0) > 0:
            self.beliefs.assert_belief("QSB lift system is recording internal communication.", 0.5, "reflection over lift dashboard")

        if mission_summary.get("active_missions", 0) >= 1:
            self.beliefs.assert_belief("QSB mission floor is tracking long-running work.", 0.45, "reflection over mission dashboard")

        reflection_text = "\n".join(lessons)

        try:
            self.semantic.add("reflection", reflection_text)
        except Exception:
            pass

        self.graph.add_edge("Reflection Engine", "reviewed", "Memory Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Department State Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Mission Floor", 1.0, "reflection")
        self.graph.add_edge("Reflection Engine", "reviewed", "Lift System", 1.0, "reflection")

        return {
            "ts": self.now(),
            "lessons": lessons,
            "belief_dashboard": self.beliefs.dashboard()
        }
