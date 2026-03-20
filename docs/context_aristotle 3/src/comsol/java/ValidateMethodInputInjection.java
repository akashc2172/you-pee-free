// ==========================================================================
// ValidateMethodInputInjection — COMSOL 6.1 test method
// ==========================================================================
//
// Tiny method to confirm -methodinputnames/-methodinputvalues CLI flags
// work correctly. Writes the received method-call input values to a text
// file so you can verify them without running a full solve.
//
// Setup:
//   1. In Application Builder → Methods, create a method with two String
//      inputs: hole_metadata_path, design_id
//   2. Paste this code as the method body
//   3. Create a Global Definitions Method Call node for this method
//   4. Run from terminal:
//
//      comsolbatch.exe -inputfile template.mph ^
//        -methodinputnames hole_metadata_path,design_id ^
//        -methodinputvalues C:/akashcomsoltest/test.holes.json,test_001
//
//   5. Check C:\akashcomsoltest\method_input_test.txt for the values
//
// If the file contains the correct values, -methodinputnames/-methodinputvalues
// works and you can proceed to use it for the real batch.
//
// If the file is not created or has wrong values, the fallback is the
// self-discovering method using model.getFilePath().
// ==========================================================================

// For App Builder: these come from method inputs
// For Java Shell: uncomment and edit the lines below
// String hole_metadata_path = "C:/akashcomsoltest/test.holes.json";
// String design_id = "test_001";

StringBuilder _out = new StringBuilder();
_out.append("=== ValidateMethodInputInjection ===\n");
_out.append("hole_metadata_path = ").append(hole_metadata_path).append("\n");
_out.append("design_id = ").append(design_id).append("\n");

// Also test model.getFilePath() for self-discovery fallback
String _modelFilePath = "";
try {
  _modelFilePath = model.getFilePath();
} catch (Exception _e) {
  _modelFilePath = "ERROR: " + _e.getMessage();
}
_out.append("model.getFilePath() = ").append(_modelFilePath).append("\n");

// Write output next to the sidecar (or to a known location)
String _outputDir = "";
if (hole_metadata_path != null && hole_metadata_path.length() > 0) {
  java.nio.file.Path _sidecarPath = java.nio.file.Paths.get(hole_metadata_path);
  _outputDir = _sidecarPath.getParent().toString();
} else if (_modelFilePath != null && _modelFilePath.length() > 0 && !_modelFilePath.startsWith("ERROR")) {
  _outputDir = java.nio.file.Paths.get(_modelFilePath).getParent().toString();
} else {
  _outputDir = System.getProperty("user.dir");
}

java.nio.file.Path _outputFile = java.nio.file.Paths.get(_outputDir, "method_input_test.txt");
try {
  java.nio.file.Files.write(
    _outputFile,
    _out.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8)
  );
} catch (Exception _e) {
  throw new RuntimeException("Failed to write test output: " + _outputFile.toString() + " — " + _e.getMessage());
}
