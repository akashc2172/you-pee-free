### COMSOL Java Method Checklist

Practical rules for writing Application Builder methods that compile and behave reliably in batch runs.

---

### 1. Java style: keep it “boring”

- Use simple, old‑school Java:
  - `for` loops, `if/else`, `switch`, `StringBuilder`, `ArrayList`.
  - Avoid generics, lambdas, streams, anonymous/inner classes, and clever comparators.
- Prefer explicit types and casts:
  - `Double.valueOf(...)`, `(String) list.get(i)`, etc.

---

### 2. Handle all checked exceptions

- Wrap file I/O and helpers that declare `throws Exception`:

```java
String raw = "";
try {
  raw = new String(
    java.nio.file.Files.readAllBytes(path),
    java.nio.charset.StandardCharsets.UTF_8
  );
} catch (Exception e) {
  throw new RuntimeException("Failed to read sidecar: " + e.getMessage());
}
```

- Re‑throw as `RuntimeException` with a clear message instead of letting checked exceptions leak.

---

### 3. Use the correct model root

Different parts of the model live in different namespaces:

- Global selections / datasets:
  - `model.selection()`
  - `model.result().dataset()`
- Component‑scoped:
  - `model.component("comp1").selection()`
  - `model.component("comp1").geom("geom1")`
  - `model.component("comp1").physics("spf")`
- Results numericals:
  - `model.result().numerical()`

**Rule:** always mirror how you built it in the GUI. If a node is under `Results → Datasets`, use `model.result().dataset()`, etc.

---

### 4. Feature types and property keys must match COMSOL

- Use the exact feature type strings:
  - Cut planes: `model.result().dataset().create(tag, "CutPlane");`
  - Surface integrals: `model.result().numerical().create(tag, "IntSurface");`
- Use the exact keys COMSOL uses:

```java
dataset.set("data", "dset2");
dataset.set("planetype", "general");
dataset.set("genmethod", "pointnormal");
dataset.set("genpnpoint", new String[] { cx, cy, cz });
dataset.set("genpnvec",   new String[] { nx, ny, nz });

num.set("data", cpTag);
num.set("expr",  new String[] { expr });
num.set("unit",  new String[] { "m^3/s" });
```

**Never invent keys.** Create one example in the GUI, view/copy the generated code, and copy the type + keys exactly.

---

### 5. Units and value types

- Geometry/physics settings often take **doubles**:

```java
feature.set("pos", new double[] { cx, cy, cz });
feature.set("r", rMm);
```

- Result datasets and expressions usually take **strings with units**:

```java
String cxStr = String.format(java.util.Locale.US, "%.9f[mm]", centerXmm);
dataset.set("genpnpoint", new String[] { cxStr, cyStr, czStr });
```

**Rule:** follow the GUI:
- if the field shows a free‑text with units, use strings like `"1.23[mm]"`;
- if it’s numeric with units only in the label, use `double`/`double[]`.

---

### 6. Always use `String[]` for multi‑valued properties

Many APIs expect arrays even for a single expression:

```java
num.set("expr",  new String[] { signedExpr });
num.set("descr", new String[] { "Signed flux" });
num.set("unit",  new String[] { "m^3/s" });
```

Passing a bare `String` may compile but will misbehave at runtime.

---

### 7. Idempotent reruns: clean up by prefix

Before creating new nodes, remove any managed ones by prefix:

```java
String[] dsTags = model.result().dataset().tags();
for (int i = 0; i < dsTags.length; i++) {
  if (dsTags[i].startsWith("CP_shaft_")) {
    model.result().dataset().remove(dsTags[i]);
  }
}

String[] numTags = model.result().numerical().tags();
for (int i = 0; i < numTags.length; i++) {
  if (numTags[i].startsWith("DV_hole_shaft_")) {
    model.result().numerical().remove(numTags[i]);
  }
}
```

Define clear, unique prefixes for each method:

- Datasets: `CP_shaft_`, `CP_coil_`, etc.
- Numericals: `DV_hole_shaft_`, `DV_hole_coil_`, etc.

---

### 8. Robust solution / dataset lookup

Do not hard‑code `"dset2"`/`"sol1"` without fallback. Use:

```java
String solutionDatasetTag = null;
String[] tags = model.result().dataset().tags();

String[] preferred = new String[] { "dset2", "dset1" };
for (int pi = 0; pi < preferred.length && solutionDatasetTag == null; pi++) {
  for (int di = 0; di < tags.length; di++) {
    if (preferred[pi].equals(tags[di])) { solutionDatasetTag = preferred[pi]; break; }
  }
}

if (solutionDatasetTag == null) {
  for (int di = 0; di < tags.length; di++) {
    try {
      if ("Solution".equals(model.result().dataset(tags[di]).getType())) {
        solutionDatasetTag = tags[di]; break;
      }
    } catch (Exception ignore) {}
  }
}

if (solutionDatasetTag == null) {
  throw new RuntimeException("Could not find a compatible solution dataset.");
}

String solutionTag = "sol1";
try {
  String solRef = model.result().dataset(solutionDatasetTag).getString("solution");
  if (solRef != null && solRef.trim().length() > 0) solutionTag = solRef.trim();
} catch (Exception ignore) {}
```

Then use `model.sol(solutionTag).getSolutioninfo()` to get `SolutionInfo`, outer/inner solnums, and `p_ramp` values.

---

### 9. Prefer exceptions over logging

- Rely on `RuntimeException` with clear messages:

```java
throw new RuntimeException("No shaft holes found in sidecar: " + sidecarPath.toString());
```

- Avoid `ModelUtil.log(...)` unless you’ve verified it’s available and imported; it can cause compilation issues in some contexts.

---

### 10. Overall structure

For each method, keep a simple, linear structure:

1. Resolve inputs (method inputs + fallback to `model.getFilePath()`).
2. Read sidecar / input files (with `try/catch`).
3. Parse into arrays using explicit regex and loops.
4. Clean up managed nodes by prefix.
5. Discover solution dataset/solution tag.
6. Create datasets (e.g., `CutPlane`) and numericals (`IntSurface`) in loops.
7. Evaluate across all outer solution numbers (`SolutionInfo`).
8. Build CSV in `StringBuilder` and write via `java.nio.file.Files.write`.

Avoid deep helper method chains and fancy abstractions; favor a single, explicit “script‑like” method body with clearly separated sections.

