import clingo
import sys

# Add the path to your project directory where the parser module is located
sys.path.append("C:\\Users\\Ahmed Khalid\\Desktop\\Defeasible-Deontic-Logic\\Python")
import parser

SHOW_RAW_MODEL = "--raw" in sys.argv

ctl = clingo.Control(["0", "--warn=no-atom-undefined"])

engine_files = [
    "language.asp",
    "Basic/language.asp",
    "Deontic/language.asp",
    "Deontic/defeasible-ab.asp",
    # "Deontic/deontic.asp",
    "Deontic/deontic-comp.asp"
]

rule_files = [ 
    # "Examples/ambiguity.dl" 
    "Scenarios/Scenario 2.dl"
    ]

for file in engine_files:
    ctl.load(file)

for f in rule_files:
    p = parser.DDLParser()
    with open(f, "r", encoding="utf-8") as theory:
        content = theory.read()

    p.parse(content)

    with open("simple.lp", "w", encoding="utf-8") as output_file:
        output_file.write(p.get_output())

    ctl.add("base", [], p.get_output())

# ctl.load("Examples/output.lp")
# ctl.load("Deontic/debug.lp")

# for f in rule_files:
#     ctl.load(f)

ctl.ground([("base", ())])

modelNo = 1

# for model in ctl.solve(yield_=True):
#     print(f"\n==============================")
#     print(f"   FINAL SCENARIO OUTCOME")
#     print(f"==============================\n")
    
#     # Define the only outputs we actually care to see
#     important_terms = ["obligation", "weakViolation", "terminalViolation", "compensate"]
    
#     for symbol in model.symbols(shown=True):
#         if symbol.name in important_terms:
#             # Print the clean result
#             print(f"--> {symbol}")
            
#     print(f"\n==============================")

# for model in ctl.solve(yield_=True):
#     print(f"\nModel: {modelNo}")
#     modelNo += 1
#     for symbol in model.symbols(shown=True):
#         print(symbol)
#         # if symbol.name == "obligation":
#         #     print (f"--> There is an obligation for {symbol.arguments[0]}")
#         # if symbol.name == "refuted":
#         #     if symbol.arguments[0].name == "non":
#         #         print (f"~{symbol.arguments[0].arguments[0]}")

for model in ctl.solve(yield_=True):
    print(f"\n{'='*50}")
    print(f"FINAL DEONTIC OUTCOME (Model {modelNo})")
    print(f"{'='*50}\n")
    shown_symbols = sorted(model.symbols(shown=True), key=str)

    if SHOW_RAW_MODEL:
        print("RAW ASP MODEL (shown symbols):")
        for symbol in shown_symbols:
            print(f"   {symbol}")
        print("")
    
    obligations_from_rules = []
    plain_obligations = set()
    defeated_rules = set()
    permissions_from_rules = []
    plain_permissions = set()
    defeated_permissions = set()
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
        elif name == "permission" and arity == 3:
            rule = str(args[0]); lit = str(args[1])
            permissions_from_rules.append((rule, lit))
        elif name == "permission" and arity == 1:
            plain_permissions.add(str(args[0]))
        elif name == "permissionDefeated" and arity == 3:
            rule = str(args[0])
            defeated_permissions.add(rule)
        elif name == "weakViolation":
            if arity == 1:
                weak_violations.append(str(args[0]))
            elif arity == 3:
                weak_violations_from_rules.append((str(args[0]), str(args[1])))
        elif name == "compensate" and arity == 4:
            compensations.append(f"If {args[2]} violated → {args[1]}")
        elif name == "fact" and arity == 1:
            facts.append(str(args[0]))
    
    # Final obligations with rule names
    final_obligations = []
    for rule, lit in obligations_from_rules:
        if rule not in defeated_rules:
            final_obligations.append((rule, lit))
    
    # Final rule-based permissions
    final_permissions = []
    for rule, lit in permissions_from_rules:
        if rule not in defeated_permissions:
            final_permissions.append((rule, lit))
    rule_permission_literals = {lit for _, lit in final_permissions}
    # Hide weak/derived permissions automatically implied by obligations.
    obligation_literals = {lit for _, lit in final_obligations} | plain_obligations
    final_plain_permissions = [
        lit for lit in sorted(plain_permissions)
        if lit not in rule_permission_literals and lit not in obligation_literals
    ]
    
    print("FACTS:")
    for f in facts:
        print(f"   • {f}")
    
    print("\nFINAL OBLIGATIONS:")
    if final_obligations:
        for rule, lit in final_obligations:
            print(f"   • You MUST {lit}  (rule: {rule})")
    else:
        print("   • None")
    
    print("\nFINAL PERMISSIONS:")
    if final_permissions:
        for rule, lit in final_permissions:
            if lit.startswith("non("):
                inner = lit[4:-1]
                print(f"   • You MAY NOT {inner}  (rule: {rule})")
            else:
                print(f"   • You MAY {lit}  (rule: {rule})")
        for lit in final_plain_permissions:
            if lit.startswith("non("):
                inner = lit[4:-1]
                print(f"   • You MAY NOT {inner}")
            else:
                print(f"   • You MAY {lit}")
    else:
        print("   • None")
    
    # Report only overridden obligations (defeated obligation rules), de-duplicated.
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

    # Optional: print weak violations and compensations if you want
    print("\n⚠️ WEAK VIOLATIONS (overridden obligations):")
    if overridden:
        for wv in overridden:
            print(f"   • {wv}")
    else:
        print("   • None")
    
    print("\nCOMPENSATION RULES (if any):")
    if compensations:
        for c in compensations:
            print(f"   • {c}")
    else:
        print("   • None")
    
    modelNo += 1

times = ctl.statistics['summary']['times']
print(f"\nTotal: {times['total']:.3f}")
print(f"CPU:   {times['cpu']:.3f}")

print(f"Atoms: {ctl.statistics['problem']['lp']['atoms']:.0f}")

print(f"Rules: {ctl.statistics['problem']['lp']['rules']:.0f}") 