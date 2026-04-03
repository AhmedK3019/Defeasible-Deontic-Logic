import clingo
import sys

# Add the path to your project directory where the parser module is located
sys.path.append("C:\\Users\\Ahmed Khalid\\Desktop\\Defeasible-Deontic-Logic\\Python")
import parser


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
    "Scenarios/test1.dl"
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

ctl.ground([("base", ())])

modelNo = 1

for model in ctl.solve(yield_=True):
    print(f"\n{'='*50}")
    print(f"FINAL DEONTIC OUTCOME (Model {modelNo})")
    print(f"{'='*50}\n")
    
    obligations_from_rules = []
    defeated_rules = set()
    permissions_from_rules = []
    plain_permissions = set()
    defeated_permissions = set()
    weak_violations = []
    compensations = []
    facts = []
    
    for sym in model.symbols(shown=True):
        name = sym.name
        args = sym.arguments
        arity = len(args)
        
        if name == "obligation" and arity == 3:
            rule = str(args[0]); lit = str(args[1])
            obligations_from_rules.append((rule, lit))
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
                weak_violations.append(f"{args[1]} (rule {args[0]})")
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
    final_plain_permissions = [lit for lit in sorted(plain_permissions) if lit not in rule_permission_literals]
    
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
    
    # Optional: print weak violations and compensations if you want
    print("\nWEAK VIOLATIONS (overridden obligations):")
    if weak_violations:
        for wv in weak_violations:
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
    # for symbol in model.symbols(shown=True):
    #     print(symbol)
        # if symbol.name == "obligation":
        #     print (f"--> There is an obligation for {symbol.arguments[0]}")
        # if symbol.name == "refuted":
        #     if symbol.arguments[0].name == "non":
        #         print (f"~{symbol.arguments[0].arguments[0]}")

times = ctl.statistics['summary']['times']
print(f"\nTotal: {times['total']:.3f}")
print(f"CPU:   {times['cpu']:.3f}")

print(f"Atoms: {ctl.statistics['problem']['lp']['atoms']:.0f}")

print(f"Rules: {ctl.statistics['problem']['lp']['rules']:.0f}") 