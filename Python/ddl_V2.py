import clingo
import sys
import os

# Add the path to your project directory where the parser module is located
sys.path.append(r"C:\Users\Ahmed Khalid\Desktop\Defeasible-Deontic-Logic\Python")
import parser

class DDLEngine:
    def __init__(self, root_folder):
        """
        Initializes the engine and pre-loads the static engine files.
        """
        self.root_folder = root_folder
        self.engine_files = [
            os.path.join(root_folder, "language.asp"),
            os.path.join(root_folder, "Basic", "language.asp"),
            os.path.join(root_folder, "Deontic", "language.asp"),
            os.path.join(root_folder, "Deontic", "defeasible-ab.asp"),
            os.path.join(root_folder, "Deontic", "deontic-comp.asp")
        ]

    def evaluate(self, scenario_content, debug_mode=True):
        """
        Parses the dynamic scenario, runs Clingo, prints the detailed Deontic Outcome,
        and returns the final obligations string for CARLA to act on.
        """
        ctl = clingo.Control(["0", "--warn=no-atom-undefined"])
        
        for file_path in self.engine_files:
            if os.path.exists(file_path):
                ctl.load(file_path)
            else:
                print(f"❌ CRITICAL: Engine file not found at {file_path}")

        # Parse the dynamic string directly
        p = parser.DDLParser()
        p.parse(scenario_content)
        
        # Inject the parsed rules and solve
        ctl.add("base", [], p.get_output())
        ctl.ground([("base", ())])

        verdict_output = ""

        for model in ctl.solve(yield_=True):
            if debug_mode:
                print(f"\n{'='*50}")
                print(f"FINAL DEONTIC OUTCOME")
                print(f"{'='*50}\n")
                
            shown_symbols = sorted(model.symbols(shown=True), key=str)
            
            obligations_from_rules = []
            plain_obligations = set()
            defeated_rules = set()
            weak_violations = []
            weak_violations_from_rules = []
            compensations = []
            facts = []
            
            for sym in shown_symbols:
                name = sym.name
                args = sym.arguments
                arity = len(args)
                
                if name == "obligation" and arity == 3:
                    rule = str(args[0]); lit = str(args[1])
                    obligations_from_rules.append((rule, lit))
                elif name == "obligation" and arity == 1:
                    plain_obligations.add(str(args[0]))
                elif name == "obligationDefeated" and arity == 3:
                    rule = str(args[0])
                    defeated_rules.add(rule)
                elif name == "weakViolation":
                    if arity == 1:
                        weak_violations.append(str(args[0]))
                    elif arity == 3:
                        weak_violations_from_rules.append((str(args[0]), str(args[1])))
                elif name == "compensate" and arity == 4:
                    compensations.append(f"If {args[2]} violated → {args[1]}")
                elif name == "fact" and arity == 1:
                    facts.append(str(args[0]))
            
            # 1. Final obligations with rule names
            final_obligations = []
            for rule, lit in obligations_from_rules:
                if rule not in defeated_rules:
                    final_obligations.append((rule, lit))
            
            # 2. Overridden obligations (Weak Violations)
            overridden = []
            seen_overridden = set()
            for rule, lit in weak_violations_from_rules:
                if rule in defeated_rules:
                    label = f"{lit} (rule {rule})"
                    if label not in seen_overridden:
                        seen_overridden.add(label)
                        overridden.append(label)
            
            final_obligation_literals = {lit for _, lit in final_obligations}
            for lit in weak_violations:
                if lit not in final_obligation_literals and lit not in seen_overridden:
                    seen_overridden.add(lit)
                    overridden.append(lit)

            # --- THE PRINTING BLOCK ---
            if debug_mode:
                print("FACTS:")
                for f in facts:
                    print(f"   • {f}")
                
                print("\nFINAL OBLIGATIONS:")
                if final_obligations:
                    for rule, lit in final_obligations:
                        print(f"   • You MUST {lit}  (rule: {rule})")
                else:
                    print("   • None")
                
                print("\nWEAK VIOLATIONS (overridden obligations):")
                if overridden:
                    for wv in overridden:
                        print(f"   • {wv}")
                else:
                    print("   • None")
                
                if compensations:
                    print("\nCOMPENSATION RULES (if any):")
                    for c in compensations:
                        print(f"   • {c}")
                print("\n")

            # --- PREPARE STRING FOR CARLA ---
            final_obs_strings = [lit for _, lit in final_obligations]
            verdict_output = " ".join(final_obs_strings)

        return verdict_output

# --- Optional Component Test ---
if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(current_dir)
    engine = DDLEngine(root)
    
    test_scenario = (
        "# Facts\n"
        "driving\n"
        "obstacle\n"
        "short_distance\n"
        "solid_line\n\n"
        "# Rules\n"
        "n_legal: driving, solid_line => [O]~cross_line\n"
        "n_safe: obstacle, short_distance => [O]cross_line\n\n"
        "# Superiority\n"
        "n_safe > n_legal\n"
    )
    
    print("Running isolated component test...")
    result = engine.evaluate(test_scenario, debug_mode=True)
    print(f"Sent back to CARLA: '{result}'")