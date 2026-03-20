// ==========================================================================
// ExportShaftHoleFlux — COMSOL 6.1 export-only method
// ==========================================================================
//
// This method does NOT create cut planes or derived values.
// It only reads EXISTING DV_hole_*_signed and DV_hole_*_abs nodes
// and writes the CSV.
//
// Use this AFTER BuildShaftHoleFluxLayer has already run at least once
// and the CP_/DV_ nodes already exist in the model.
//
// This is safer for debugging and re-export because it avoids
// stale-node / rerun issues from rebuilding datasets.
//
// VERSION: Works in both Application Builder and Java Shell.
//   For Java Shell: edit the two variables below.
//   For App Builder: add method inputs hole_metadata_path, design_id
//                    and change the two lines below to use them.
//
// Output: <design_id>_shaft_hole_flux.csv next to the .holes.json sidecar
// ==========================================================================

// ===================== EDIT THESE FOR JAVA SHELL =========================
// For App Builder, replace with: String holeMetadataPathLocal = hole_metadata_path;
String holeMetadataPathLocal = "C:\\akashcomsoltest\\design_0000.holes.json";
// For App Builder, replace with: String designIdLocal = design_id;
String designIdLocal = "design_0000";
// =========================================================================

String FALLBACK_SOLUTION_TAG = "sol1";
String DEFAULT_SOLUTION_DATASET_TAG = "dset2";
String FALLBACK_SOLUTION_DATASET_TAG = "dset1";
String CSV_SUFFIX = "_shaft_hole_flux.csv";

java.nio.file.Path sidecarPath = java.nio.file.Paths.get(holeMetadataPathLocal).toAbsolutePath().normalize();
if (!java.nio.file.Files.exists(sidecarPath)) {
  throw new RuntimeException("hole_metadata_path does not exist: " + sidecarPath.toString());
}

// --- Parse sidecar to get shaft hole IDs and metadata ---
String _sidecarRaw = "";
try {
  _sidecarRaw = new String(
    java.nio.file.Files.readAllBytes(sidecarPath),
    java.nio.charset.StandardCharsets.UTF_8
  );
} catch (Exception _e) {
  throw new RuntimeException("Failed to read sidecar: " + _e.getMessage());
}

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

// Collect shaft hole metadata
java.util.List _shHoleIds    = new java.util.ArrayList();
java.util.List _shRegions    = new java.util.ArrayList();
java.util.List _shAxialXmm   = new java.util.ArrayList();
java.util.List _shAxialRanks = new java.util.ArrayList();

for (int _oi = 0; _oi < _holeObjects.size(); _oi++) {
  String _obj = (String) _holeObjects.get(_oi);
  java.util.regex.Matcher _typeMatcher = java.util.regex.Pattern.compile(
    "\"type\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_typeMatcher.find()) continue;
  if (!"shaft".equals(_typeMatcher.group(1))) continue;

  java.util.regex.Matcher _idMatcher = java.util.regex.Pattern.compile(
    "\"hole_id\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_idMatcher.find()) throw new RuntimeException("Missing hole_id");
  _shHoleIds.add(_idMatcher.group(1));

  java.util.regex.Matcher _regMatcher = java.util.regex.Pattern.compile(
    "\"region\"\\s*:\\s*\"([^\"]*)\"", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_regMatcher.find()) throw new RuntimeException("Missing region");
  _shRegions.add(_regMatcher.group(1));

  java.util.regex.Matcher _axMatcher = java.util.regex.Pattern.compile(
    "\"axial_x_mm\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_axMatcher.find()) throw new RuntimeException("Missing axial_x_mm");
  _shAxialXmm.add(Double.valueOf(Double.parseDouble(_axMatcher.group(1))));

  java.util.regex.Matcher _arMatcher = java.util.regex.Pattern.compile(
    "\"axial_rank\"\\s*:\\s*(-?[0-9]+(?:\\.[0-9]+)?(?:[eE][+-]?[0-9]+)?)", java.util.regex.Pattern.DOTALL
  ).matcher(_obj);
  if (!_arMatcher.find()) throw new RuntimeException("Missing axial_rank");
  _shAxialRanks.add(Integer.valueOf((int) Math.round(Double.parseDouble(_arMatcher.group(1)))));
}

int _nHoles = _shHoleIds.size();
if (_nHoles == 0) {
  throw new RuntimeException("No shaft holes found in sidecar.");
}

// Copy to arrays and bubble sort
String[] holeIds     = new String[_nHoles];
String[] regions     = new String[_nHoles];
double[] axialXmm    = new double[_nHoles];
int[]    axialRanks  = new int[_nHoles];
String[] signedTags  = new String[_nHoles];
String[] absTags     = new String[_nHoles];

for (int _i = 0; _i < _nHoles; _i++) {
  holeIds[_i]    = (String) _shHoleIds.get(_i);
  regions[_i]    = (String) _shRegions.get(_i);
  axialXmm[_i]   = ((Double) _shAxialXmm.get(_i)).doubleValue();
  axialRanks[_i] = ((Integer) _shAxialRanks.get(_i)).intValue();
}

for (int _i = 0; _i < _nHoles - 1; _i++) {
  for (int _j = 0; _j < _nHoles - 1 - _i; _j++) {
    boolean _swap = false;
    if (axialRanks[_j] > axialRanks[_j + 1]) {
      _swap = true;
    } else if (axialRanks[_j] == axialRanks[_j + 1]) {
      if (holeIds[_j].compareTo(holeIds[_j + 1]) > 0) _swap = true;
    }
    if (_swap) {
      String _tmpS; double _tmpD; int _tmpI;
      _tmpS = holeIds[_j];    holeIds[_j]    = holeIds[_j+1];    holeIds[_j+1]    = _tmpS;
      _tmpS = regions[_j];    regions[_j]    = regions[_j+1];    regions[_j+1]    = _tmpS;
      _tmpD = axialXmm[_j];   axialXmm[_j]   = axialXmm[_j+1];   axialXmm[_j+1]   = _tmpD;
      _tmpI = axialRanks[_j]; axialRanks[_j] = axialRanks[_j+1]; axialRanks[_j+1] = _tmpI;
    }
  }
}

for (int _i = 0; _i < _nHoles; _i++) {
  signedTags[_i] = "DV_hole_" + holeIds[_i] + "_signed";
  absTags[_i]    = "DV_hole_" + holeIds[_i] + "_abs";
}

// --- Find solution info ---
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

// --- Evaluate existing nodes and write CSV ---
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
    double _signedVal = Double.NaN;
    try {
      double[][] _sVals;
      if (_outerSolnum > 0) _sVals = model.result().numerical(signedTags[_h]).getReal(_outerSolnum);
      else                  _sVals = model.result().numerical(signedTags[_h]).getReal();
      if (_sVals != null && _sVals.length > 0 && _sVals[0].length > 0) _signedVal = _sVals[0][0];
    } catch (Exception _ignore) {}

    double _absVal = Double.NaN;
    try {
      double[][] _aVals;
      if (_outerSolnum > 0) _aVals = model.result().numerical(absTags[_h]).getReal(_outerSolnum);
      else                  _aVals = model.result().numerical(absTags[_h]).getReal();
      if (_aVals != null && _aVals.length > 0 && _aVals[0].length > 0) _absVal = _aVals[0][0];
    } catch (Exception _ignore) {}

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

java.nio.file.Path _outputCsv = sidecarPath.resolveSibling(designIdLocal + CSV_SUFFIX);
try {
  java.nio.file.Files.write(
    _outputCsv,
    _csv.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)
  );
} catch (Exception _e) {
  throw new RuntimeException("Failed to write CSV: " + _outputCsv.toString() + " — " + _e.getMessage());
}
