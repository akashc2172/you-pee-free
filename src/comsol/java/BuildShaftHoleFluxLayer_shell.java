// ==========================================================================
// BuildShaftHoleFluxLayer — COMSOL 6.1 Java Shell version
// ==========================================================================
//
// Paste this entire block into:   Home → Windows → Java Shell
//
// INPUT MODES (in priority order):
//   1. Edit the two variables below (for manual single-design runs)
//   2. Leave them empty → auto-discovers from model.getFilePath()
//      (e.g. if output .mph is design_0001.mph, finds design_0001.holes.json
//       in the same directory)
//
// Output: <design_id>_shaft_hole_flux.csv next to the .holes.json sidecar.
//
// Naming contract:
//   CP_<hole_id>                 — cut plane dataset
//   DV_hole_<hole_id>_signed     — signed local flux integration
//   DV_hole_<hole_id>_abs        — absolute local flux integration
//
// IMPORTANT: This file does NOT use model.param().get() because
// COMSOL Parameters treat values as numeric expressions, which
// breaks on file paths and arbitrary strings.
// ==========================================================================

// ===================== EDIT THESE (or leave empty for auto-discover) =======
String holeMetadataPath = "";
String designId = "";
// =========================================================================

// --- Self-discovery fallback via model.getFilePath() ---
if (holeMetadataPath == null || holeMetadataPath.trim().length() == 0
    || designId == null || designId.trim().length() == 0) {
  String _mphPath = model.getFilePath();
  if (_mphPath != null && _mphPath.trim().length() > 0) {
    java.nio.file.Path _mphFile = java.nio.file.Paths.get(_mphPath.trim());
    String _mphName = _mphFile.getFileName().toString();
    if (_mphName.endsWith(".mph")) {
      _mphName = _mphName.substring(0, _mphName.length() - 4);
    }
    if (designId == null || designId.trim().length() == 0) {
      designId = _mphName;
    }
    if (holeMetadataPath == null || holeMetadataPath.trim().length() == 0) {
      java.nio.file.Path _inferred = _mphFile.getParent().resolve(_mphName + ".holes.json");
      if (java.nio.file.Files.exists(_inferred)) {
        holeMetadataPath = _inferred.toString();
      }
    }
  }
}
if (holeMetadataPath == null || holeMetadataPath.trim().length() == 0) {
  throw new RuntimeException("Could not resolve hole_metadata_path (set manually or ensure .holes.json is next to the .mph)");
}
if (designId == null || designId.trim().length() == 0) {
  throw new RuntimeException("Could not resolve design_id (set manually or ensure model is saved)");
}

String DEFAULT_SOLUTION_DATASET_TAG = "dset2";
String FALLBACK_SOLUTION_DATASET_TAG = "dset1";
String FALLBACK_SOLUTION_TAG = "sol1";
String CSV_SUFFIX = "_shaft_hole_flux.csv";
String MANAGED_DATASET_PREFIX = "CP_shaft_";
String MANAGED_NUMERICAL_PREFIX = "DV_hole_shaft_";
String DEFAULT_VEL_X = "u";
String DEFAULT_VEL_Y = "v";
String DEFAULT_VEL_Z = "w";

java.nio.file.Path sidecarPath = java.nio.file.Paths.get(holeMetadataPath).toAbsolutePath().normalize();
if (!java.nio.file.Files.exists(sidecarPath)) {
  throw new RuntimeException("hole_metadata_path does not exist: " + sidecarPath.toString());
}

// ==========================================================================
// PARSE SIDECAR — extract shaft holes into parallel arrays
// ==========================================================================

String _sidecarRaw = "";
try {
  _sidecarRaw = new String(
    java.nio.file.Files.readAllBytes(sidecarPath),
    java.nio.charset.StandardCharsets.UTF_8
  );
} catch (Exception _e) {
  throw new RuntimeException("Failed to read sidecar: " + _e.getMessage());
}

// --- Extract the "holes" array body ---
int _holesKeyIdx = _sidecarRaw.indexOf("\"holes\"");
if (_holesKeyIdx < 0) throw new RuntimeException("Could not find sidecar key: holes");
int _holesArrStart = _sidecarRaw.indexOf("[", _holesKeyIdx);
if (_holesArrStart < 0) throw new RuntimeException("Could not find array start for key: holes");

int _holesDepth = 0;
int _holesArrEnd = -1;
for (int _hi = _holesArrStart; _hi < _sidecarRaw.length(); _hi++) {
  char _hc = _sidecarRaw.charAt(_hi);
  if (_hc == '[') _holesDepth++;
  else if (_hc == ']') { _holesDepth--; if (_holesDepth == 0) { _holesArrEnd = _hi; break; } }
}
if (_holesArrEnd < 0) throw new RuntimeException("Could not find array end for key: holes");
String _holesArrayBody = _sidecarRaw.substring(_holesArrStart + 1, _holesArrEnd);

// --- Split into individual hole objects ---
java.util.List _holeObjects = new java.util.ArrayList();
{
  int _soDepth = 0; int _soStart = -1;
  boolean _soInStr = false; boolean _soEsc = false;
  for (int _si = 0; _si < _holesArrayBody.length(); _si++) {
    char _sc = _holesArrayBody.charAt(_si);
    if (_soEsc) { _soEsc = false; continue; }
    if (_sc == '\\') { _soEsc = true; continue; }
    if (_sc == '"') { _soInStr = !_soInStr; continue; }
    if (_soInStr) continue;
    if (_sc == '{') { if (_soDepth == 0) _soStart = _si; _soDepth++; }
    else if (_sc == '}') { _soDepth--; if (_soDepth == 0 && _soStart >= 0) { _holeObjects.add(_holesArrayBody.substring(_soStart, _si + 1)); _soStart = -1; } }
  }
}

// --- Filter shaft holes and collect into parallel lists ---
java.util.List _shHoleIds     = new java.util.ArrayList();
java.util.List _shRegions     = new java.util.ArrayList();
java.util.List _shAxialXmm    = new java.util.ArrayList();
java.util.List _shAxialRanks  = new java.util.ArrayList();
java.util.List _shCenterXmm   = new java.util.ArrayList();
java.util.List _shCenterYmm   = new java.util.ArrayList();
java.util.List _shCenterZmm   = new java.util.ArrayList();
java.util.List _shNormalX      = new java.util.ArrayList();
java.util.List _shNormalY      = new java.util.ArrayList();
java.util.List _shNormalZ      = new java.util.ArrayList();
java.util.List _shMaskRadius   = new java.util.ArrayList();

for (int _oi = 0; _oi < _holeObjects.size(); _oi++) {
  String _obj = (String) _holeObjects.get(_oi);

  // Extract type
  java.util.regex.Matcher _typeMatcher = java.util.regex.Pattern.compile(
    "\"type\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_typeMatcher.find()) continue;
  if (!"shaft".equals(_typeMatcher.group(1))) continue;

  // Extract hole_id
  java.util.regex.Matcher _idMatcher = java.util.regex.Pattern.compile(
    "\"hole_id\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_idMatcher.find()) throw new RuntimeException("Missing hole_id in shaft hole object");
  _shHoleIds.add(_idMatcher.group(1));

  // Extract region
  java.util.regex.Matcher _regMatcher = java.util.regex.Pattern.compile(
    "\"region\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_regMatcher.find()) throw new RuntimeException("Missing region in shaft hole object");
  _shRegions.add(_regMatcher.group(1));

  // Extract axial_x_mm
  java.util.regex.Matcher _axMatcher = java.util.regex.Pattern.compile(
    "\"axial_x_mm\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_axMatcher.find()) throw new RuntimeException("Missing axial_x_mm");
  _shAxialXmm.add(Double.valueOf(Double.parseDouble(_axMatcher.group(1))));

  // Extract axial_rank
  java.util.regex.Matcher _arMatcher = java.util.regex.Pattern.compile(
    "\"axial_rank\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_arMatcher.find()) throw new RuntimeException("Missing axial_rank");
  _shAxialRanks.add(Integer.valueOf((int) Math.round(Double.parseDouble(_arMatcher.group(1)))));

  // Extract center_mm array
  java.util.regex.Matcher _cMatcher = java.util.regex.Pattern.compile(
    "\"center_mm\"\\s*:\\s*\\[([^\\]]*)\\]", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_cMatcher.find()) throw new RuntimeException("Missing center_mm");
  String[] _cParts = _cMatcher.group(1).split(",");
  _shCenterXmm.add(Double.valueOf(Double.parseDouble(_cParts[0].trim())));
  _shCenterYmm.add(Double.valueOf(Double.parseDouble(_cParts[1].trim())));
  _shCenterZmm.add(Double.valueOf(Double.parseDouble(_cParts[2].trim())));

  // Extract normal array
  java.util.regex.Matcher _nMatcher = java.util.regex.Pattern.compile(
    "\"normal\"\\s*:\\s*\\[([^\\]]*)\\]", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_nMatcher.find()) throw new RuntimeException("Missing normal");
  String[] _nParts = _nMatcher.group(1).split(",");
  _shNormalX.add(Double.valueOf(Double.parseDouble(_nParts[0].trim())));
  _shNormalY.add(Double.valueOf(Double.parseDouble(_nParts[1].trim())));
  _shNormalZ.add(Double.valueOf(Double.parseDouble(_nParts[2].trim())));

  // Extract mask radius: prefer selection_cylinder_radius_mm, fallback to radius_mm
  java.util.regex.Matcher _srMatcher = java.util.regex.Pattern.compile(
    "\"selection_cylinder_radius_mm\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (_srMatcher.find()) {
    _shMaskRadius.add(Double.valueOf(Double.parseDouble(_srMatcher.group(1))));
  } else {
    java.util.regex.Matcher _rrMatcher = java.util.regex.Pattern.compile(
      "\"radius_mm\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
    ).matcher(_obj);
    if (!_rrMatcher.find()) throw new RuntimeException("Missing radius_mm");
    _shMaskRadius.add(Double.valueOf(Double.parseDouble(_rrMatcher.group(1))));
  }
}

int _nHoles = _shHoleIds.size();
if (_nHoles == 0) {
  throw new RuntimeException("No shaft holes found in sidecar: " + sidecarPath.toString());
}

// --- Manual bubble sort by axial_rank, then hole_id (no anonymous comparators) ---
String[]  holeIds    = new String[_nHoles];
String[]  regions    = new String[_nHoles];
double[]  axialXmm   = new double[_nHoles];
int[]     axialRanks = new int[_nHoles];
double[]  centerXmm  = new double[_nHoles];
double[]  centerYmm  = new double[_nHoles];
double[]  centerZmm  = new double[_nHoles];
double[]  normalX    = new double[_nHoles];
double[]  normalY    = new double[_nHoles];
double[]  normalZ    = new double[_nHoles];
double[]  maskRadius = new double[_nHoles];
String[]  cpTags     = new String[_nHoles];
String[]  signedTags = new String[_nHoles];
String[]  absTags    = new String[_nHoles];

for (int _i = 0; _i < _nHoles; _i++) {
  holeIds[_i]    = (String) _shHoleIds.get(_i);
  regions[_i]    = (String) _shRegions.get(_i);
  axialXmm[_i]   = ((Double) _shAxialXmm.get(_i)).doubleValue();
  axialRanks[_i] = ((Integer) _shAxialRanks.get(_i)).intValue();
  centerXmm[_i]  = ((Double) _shCenterXmm.get(_i)).doubleValue();
  centerYmm[_i]  = ((Double) _shCenterYmm.get(_i)).doubleValue();
  centerZmm[_i]  = ((Double) _shCenterZmm.get(_i)).doubleValue();
  normalX[_i]    = ((Double) _shNormalX.get(_i)).doubleValue();
  normalY[_i]    = ((Double) _shNormalY.get(_i)).doubleValue();
  normalZ[_i]    = ((Double) _shNormalZ.get(_i)).doubleValue();
  maskRadius[_i] = ((Double) _shMaskRadius.get(_i)).doubleValue();
}

// Bubble sort (COMSOL method editor chokes on anonymous comparators)
for (int _i = 0; _i < _nHoles - 1; _i++) {
  for (int _j = 0; _j < _nHoles - 1 - _i; _j++) {
    boolean _swap = false;
    if (axialRanks[_j] > axialRanks[_j + 1]) {
      _swap = true;
    } else if (axialRanks[_j] == axialRanks[_j + 1]) {
      if (holeIds[_j].compareTo(holeIds[_j + 1]) > 0) {
        _swap = true;
      }
    }
    if (_swap) {
      String  _tmpS;
      double  _tmpD;
      int     _tmpI;
      _tmpS = holeIds[_j];    holeIds[_j]    = holeIds[_j+1];    holeIds[_j+1]    = _tmpS;
      _tmpS = regions[_j];    regions[_j]    = regions[_j+1];    regions[_j+1]    = _tmpS;
      _tmpD = axialXmm[_j];   axialXmm[_j]   = axialXmm[_j+1];   axialXmm[_j+1]   = _tmpD;
      _tmpI = axialRanks[_j]; axialRanks[_j] = axialRanks[_j+1]; axialRanks[_j+1] = _tmpI;
      _tmpD = centerXmm[_j];  centerXmm[_j]  = centerXmm[_j+1];  centerXmm[_j+1]  = _tmpD;
      _tmpD = centerYmm[_j];  centerYmm[_j]  = centerYmm[_j+1];  centerYmm[_j+1]  = _tmpD;
      _tmpD = centerZmm[_j];  centerZmm[_j]  = centerZmm[_j+1];  centerZmm[_j+1]  = _tmpD;
      _tmpD = normalX[_j];    normalX[_j]    = normalX[_j+1];    normalX[_j+1]    = _tmpD;
      _tmpD = normalY[_j];    normalY[_j]    = normalY[_j+1];    normalY[_j+1]    = _tmpD;
      _tmpD = normalZ[_j];    normalZ[_j]    = normalZ[_j+1];    normalZ[_j+1]    = _tmpD;
      _tmpD = maskRadius[_j]; maskRadius[_j] = maskRadius[_j+1]; maskRadius[_j+1] = _tmpD;
    }
  }
}

// Build tag names after sort
for (int _i = 0; _i < _nHoles; _i++) {
  cpTags[_i]     = "CP_" + holeIds[_i];
  signedTags[_i] = "DV_hole_" + holeIds[_i] + "_signed";
  absTags[_i]    = "DV_hole_" + holeIds[_i] + "_abs";
}

// ==========================================================================
// CLEAN UP any previously managed nodes
// ==========================================================================

try {
  String[] _dsTags = model.result().dataset().tags();
  for (int _di = 0; _di < _dsTags.length; _di++) {
    if (_dsTags[_di].startsWith(MANAGED_DATASET_PREFIX)) {
      model.result().dataset().remove(_dsTags[_di]);
    }
  }
} catch (Exception _ignore) {}

try {
  String[] _numTags = model.result().numerical().tags();
  for (int _ni = 0; _ni < _numTags.length; _ni++) {
    if (_numTags[_ni].startsWith(MANAGED_NUMERICAL_PREFIX)) {
      model.result().numerical().remove(_numTags[_ni]);
    }
  }
} catch (Exception _ignore) {}

// ==========================================================================
// FIND solution dataset
// ==========================================================================

String solutionDatasetTag = null;
{
  String[] _dsCheckTags = model.result().dataset().tags();
  String[] _preferred = new String[] { DEFAULT_SOLUTION_DATASET_TAG, FALLBACK_SOLUTION_DATASET_TAG };
  for (int _pi = 0; _pi < _preferred.length && solutionDatasetTag == null; _pi++) {
    for (int _di = 0; _di < _dsCheckTags.length; _di++) {
      if (_preferred[_pi].equals(_dsCheckTags[_di])) { solutionDatasetTag = _preferred[_pi]; break; }
    }
  }
  if (solutionDatasetTag == null) {
    for (int _di = 0; _di < _dsCheckTags.length; _di++) {
      try {
        String _dsType = model.result().dataset(_dsCheckTags[_di]).getType();
        if ("Solution".equals(_dsType)) { solutionDatasetTag = _dsCheckTags[_di]; break; }
      } catch (Exception _ignore) {}
    }
  }
  if (solutionDatasetTag == null) {
    throw new RuntimeException("Could not find a compatible solution dataset.");
  }
}

String solutionTag = FALLBACK_SOLUTION_TAG;
try {
  String _solRef = model.result().dataset(solutionDatasetTag).getString("solution");
  if (_solRef != null && _solRef.trim().length() > 0) solutionTag = _solRef.trim();
} catch (Exception _ignore) {}

// ==========================================================================
// CREATE cut planes and derived values for each shaft hole
// ==========================================================================

for (int _h = 0; _h < _nHoles; _h++) {
  String _mmCx = String.format(java.util.Locale.US, "%.9f[mm]", centerXmm[_h]);
  String _mmCy = String.format(java.util.Locale.US, "%.9f[mm]", centerYmm[_h]);
  String _mmCz = String.format(java.util.Locale.US, "%.9f[mm]", centerZmm[_h]);
  String _sNx  = String.format(java.util.Locale.US, "%.12f", normalX[_h]);
  String _sNy  = String.format(java.util.Locale.US, "%.12f", normalY[_h]);
  String _sNz  = String.format(java.util.Locale.US, "%.12f", normalZ[_h]);

  // Mask expression
  String _mmMr = String.format(java.util.Locale.US, "%.9f[mm]", maskRadius[_h]);
  String _maskExpr = String.format(java.util.Locale.US,
    "if((x-(%s))^2 + (y-(%s))^2 + (z-(%s))^2 <= (%s)^2, 1, 0)",
    _mmCx, _mmCy, _mmCz, _mmMr);

  // Flux expressions
  String _localFlux = String.format(java.util.Locale.US,
    "((%s)*(%s) + (%s)*(%s) + (%s)*(%s))",
    _sNx, DEFAULT_VEL_X, _sNy, DEFAULT_VEL_Y, _sNz, DEFAULT_VEL_Z);
  String _signedExpr = "(" + _localFlux + ")*(" + _maskExpr + ")";
  String _absExpr    = "(abs(" + _localFlux + "))*(" + _maskExpr + ")";

  // --- Cut Plane ---
  model.result().dataset().create(cpTags[_h], "CutPlane");
  model.result().dataset(cpTags[_h]).label("Shaft hole cut plane: " + holeIds[_h]);
  model.result().dataset(cpTags[_h]).set("data", solutionDatasetTag);
  model.result().dataset(cpTags[_h]).set("planetype", "general");
  model.result().dataset(cpTags[_h]).set("genmethod", "pointnormal");
  model.result().dataset(cpTags[_h]).set("genpnpoint", new String[] { _mmCx, _mmCy, _mmCz });
  model.result().dataset(cpTags[_h]).set("genpnvec",   new String[] { _sNx,  _sNy,  _sNz  });

  // --- Signed DV ---
  model.result().numerical().create(signedTags[_h], "IntSurface");
  model.result().numerical(signedTags[_h]).label("Signed local flux: " + holeIds[_h]);
  model.result().numerical(signedTags[_h]).set("data", cpTags[_h]);
  model.result().numerical(signedTags[_h]).set("expr",  new String[] { _signedExpr });
  model.result().numerical(signedTags[_h]).set("descr", new String[] { "Signed local hole flux" });
  model.result().numerical(signedTags[_h]).set("unit",  new String[] { "m^3/s" });

  // --- Absolute DV ---
  model.result().numerical().create(absTags[_h], "IntSurface");
  model.result().numerical(absTags[_h]).label("Absolute local flux: " + holeIds[_h]);
  model.result().numerical(absTags[_h]).set("data", cpTags[_h]);
  model.result().numerical(absTags[_h]).set("expr",  new String[] { _absExpr });
  model.result().numerical(absTags[_h]).set("descr", new String[] { "Absolute local hole flux" });
  model.result().numerical(absTags[_h]).set("unit",  new String[] { "m^3/s" });
}

// ==========================================================================
// EVALUATE and write CSV
// ==========================================================================

com.comsol.model.SolutionInfo _solInfo = null;
int[] _outerSolnums = null;
try {
  _solInfo = model.sol(solutionTag).getSolutioninfo();
  _outerSolnums = _solInfo.getOuterSolnum();
} catch (Exception _ignore) {}
if (_outerSolnums == null || _outerSolnums.length == 0) {
  _outerSolnums = new int[] { 0 };
}

StringBuilder _csv = new StringBuilder();
_csv.append("hole_id,axial_x_mm,region,type,p_ramp,signed_flux_m3s,abs_flux_m3s\n");

for (int _si = 0; _si < _outerSolnums.length; _si++) {
  int _outerSolnum = _outerSolnums[_si];

  // Lookup p_ramp for this solution step
  Double _pRamp = null;
  if (_solInfo != null) {
    try {
      int[] _innerSolnums = _solInfo.getSolnum(_outerSolnum, false);
      int _innerSolnum = 1;
      if (_innerSolnums != null && _innerSolnums.length > 0 && _innerSolnums[0] > 0)
        _innerSolnum = _innerSolnums[0];
      int[][] _solnums = new int[][] { new int[] { _outerSolnum, _innerSolnum } };
      String[][] _pnames = _solInfo.getPNames(_solnums);
      double[][] _pvals  = _solInfo.getPvals(_solnums);
      if (_pnames != null && _pvals != null && _pnames.length > 0 && _pvals.length > 0) {
        for (int _pi = 0; _pi < _pnames[0].length; _pi++) {
          if ("p_ramp".equals(_pnames[0][_pi])) {
            _pRamp = Double.valueOf(_pvals[0][_pi]);
            break;
          }
        }
      }
    } catch (Exception _ignore) {}
  }

  for (int _h = 0; _h < _nHoles; _h++) {
    // Evaluate signed flux — getReal() returns double[][]
    double _signedVal = Double.NaN;
    try {
      double[][] _sVals;
      if (_outerSolnum > 0) _sVals = model.result().numerical(signedTags[_h]).getReal(_outerSolnum);
      else                  _sVals = model.result().numerical(signedTags[_h]).getReal();
      if (_sVals != null && _sVals.length > 0 && _sVals[0].length > 0) _signedVal = _sVals[0][0];
    } catch (Exception _ignore) {}

    // Evaluate abs flux — getReal() returns double[][]
    double _absVal = Double.NaN;
    try {
      double[][] _aVals;
      if (_outerSolnum > 0) _aVals = model.result().numerical(absTags[_h]).getReal(_outerSolnum);
      else                  _aVals = model.result().numerical(absTags[_h]).getReal();
      if (_aVals != null && _aVals.length > 0 && _aVals[0].length > 0) _absVal = _aVals[0][0];
    } catch (Exception _ignore) {}

    // Write CSV row
    _csv.append(holeIds[_h]).append(",");
    _csv.append(String.format(java.util.Locale.US, "%.12e", axialXmm[_h])).append(",");
    _csv.append(regions[_h]).append(",");
    _csv.append("shaft").append(",");
    if (_pRamp != null && !_pRamp.isNaN() && !_pRamp.isInfinite())
      _csv.append(String.format(java.util.Locale.US, "%.12e", _pRamp.doubleValue()));
    _csv.append(",");
    if (!Double.isNaN(_signedVal) && !Double.isInfinite(_signedVal))
      _csv.append(String.format(java.util.Locale.US, "%.12e", _signedVal));
    _csv.append(",");
    if (!Double.isNaN(_absVal) && !Double.isInfinite(_absVal))
      _csv.append(String.format(java.util.Locale.US, "%.12e", _absVal));
    _csv.append("\n");
  }
}

// --- Write CSV file ---
java.nio.file.Path _outputCsv = sidecarPath.resolveSibling(designId + CSV_SUFFIX);
try {
  java.nio.file.Files.write(
    _outputCsv,
    _csv.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)
  );
} catch (Exception _e) {
  throw new RuntimeException("Failed to write CSV: " + _outputCsv.toString() + " — " + _e.getMessage());
}
