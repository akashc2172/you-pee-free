# COMSOL Automation Lessons Learned

Hard-won lessons from real testing of the Java automation layer in COMSOL 6.1.

## Storage & parameter passing

1. **Do NOT use COMSOL Parameters for string/path values.** COMSOL Parameters expect numeric expressions. File paths and design IDs cause syntax errors.
2. **Use Application Builder method inputs** for strings. They are real Java Strings in scope.
3. **CLI parameter passing (`-pname`/`-pval`) is also expression-based.** Passing Windows file paths through it is brittle. Use method inputs with saved values, or hardcoded paths in the Java Shell version.
4. **`-paramfile` had wrong delimiter/quoting assumptions** for path strings. Not the right tool here.

## Java code style in COMSOL

5. **COMSOL Method Editor is much pickier than normal Java.** Flat, boring, explicit code works. Fancy patterns break.
6. **No inner classes.** The method editor doesn't support them reliably.
7. **No anonymous comparators.** Captured local variable issues. Use manual bubble sort.
8. **No `ModelUtil.log(...)`.** Not available in the method environment.
9. **Wrap ALL file I/O in try/catch.** Checked exceptions must be handled.
10. **`getReal()` returns `double[][]`, not `double[]`.** Even for scalar results.
11. **Don't wrap the method body in a function.** The method body IS the function body.
12. **Variable shadowing is dangerous.** Use `holeMetadataPathLocal = hole_metadata_path` aliases.

## COMSOL wiring

13. **A Global Definitions Method Call node is required** before Job Sequence can see the method.
14. **Sequence ordering: solve first, then method call.** Wrong order = method runs on stale data.
15. **Running a Sequence from the GUI triggers real solve behavior.** Not a metadata-only action.

## Batch execution

16. **Use `comsolbatch.exe`, not `comsol.exe`.** The latter opens the desktop UI.
17. **COMSOL may not be on PATH.** Use full path: `C:\Program Files\COMSOL\COMSOL61\Multiphysics\bin\win64\comsolbatch.exe`
18. **Python/MATLAB may not exist on the COMSOL machine.** Don't assume.

## Windows environment

19. **Windows paths with spaces + parentheses cause quoting pain.** Use a no-spaces staging folder like `C:\akashcomsoltest`.
20. **Windows Explorer hides file extensions.** Be careful when staging `.mph`, `.step`, `.json` files.

## Architecture

21. **Export-only method is safer than rebuild.** Split into: (a) build method (creates CP_/DV_ nodes), (b) export-only method (reads existing nodes, writes CSV). The export-only method avoids stale-node collisions on reruns.
22. **Tag/prefix consistency matters.** Cleanup logic and creation tags must match exactly.
23. **Template stores method-call inputs inside `.mph`.** Multi-design looping options: (a) one template copy per design, (b) override method inputs externally.
