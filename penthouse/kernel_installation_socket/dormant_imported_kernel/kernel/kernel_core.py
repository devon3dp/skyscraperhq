from kernel.identity_core import IdentityCore
from kernel.axiom_core import AxiomCore
from kernel.continuity_core import ContinuityCore
from kernel.symbolic_core import SymbolicLogicCore
from kernel.belief_core import BeliefCore

class QSBKernelCore:
    def __init__(self):
        self.identity = IdentityCore()
        self.axioms = AxiomCore()
        self.continuity = ContinuityCore()
        self.symbols = SymbolicLogicCore()
        self.beliefs = BeliefCore()
        self.boot_state = self.continuity.boot_check()

    def status(self):
        return {
            "kernel": self.identity.status(),
            "continuity": self.boot_state,
            "axioms": self.axioms.list_axioms(),
            "symbolic_core": self.symbols.dashboard(),
            "beliefs": self.beliefs.dashboard()
        }

    def analyze(self, text, source="kernel"):
        axiom_check = self.axioms.check(text)
        symbolic_result = self.symbols.observe(source, text)
        self.beliefs.learn_from_symbolic(symbolic_result, evidence_text=text)
        return {
            "axiom_check": axiom_check,
            "symbolic_result": symbolic_result
        }
