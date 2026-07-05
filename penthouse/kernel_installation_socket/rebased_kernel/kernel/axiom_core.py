class AxiomCore:
    AXIOMS = [
        "QSB is not a model.",
        "QSB is the persistent kernel above models.",
        "Models are replaceable workers.",
        "Departments are modular floors.",
        "Lifts are controlled communication buses.",
        "Memory must persist across boots.",
        "Symbolic logic belongs inside the locked Penthouse kernel.",
        "Knowledge Graph stores relationships, but the kernel interprets meaning.",
        "Upgrades must preserve continuity.",
        "Cloud calls remain disabled unless explicitly enabled later."
    ]

    def list_axioms(self):
        return self.AXIOMS

    def check(self, text):
        lower = text.lower()
        warnings = []

        if "delete memory" in lower or "wipe memory" in lower:
            warnings.append("Memory deletion request detected. Continuity protection should review this.")

        if "cloud" in lower and "enable" in lower:
            warnings.append("Cloud enablement request detected. Offline-first rule requires explicit confirmation.")

        if "symbolic floor" in lower:
            warnings.append("Architecture correction: symbolic logic is kernel-level, not a normal floor.")

        return {
            "passed": len(warnings) == 0,
            "warnings": warnings,
            "axioms_checked": len(self.AXIOMS)
        }
