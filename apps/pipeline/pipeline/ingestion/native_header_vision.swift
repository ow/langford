// Local-only OCR for a bounded original-PDF header rendered by Python.
import Foundation
import Vision
import AppKit

let request = VNRecognizeTextRequest()
request.revision = VNRecognizeTextRequestRevision3
request.recognitionLevel = .accurate
request.recognitionLanguages = ["en-US"]
request.usesLanguageCorrection = true
try VNImageRequestHandler(url: URL(fileURLWithPath: CommandLine.arguments[1])).perform([request])
let lines = (request.results ?? []).map { observation -> [String: Any] in
    let b = observation.boundingBox
    return [
        "bounding_box": [b.minX, b.minY, b.width, b.height],
        "candidates": observation.topCandidates(3).map {
            ["text": $0.string, "confidence": $0.confidence] as [String: Any]
        },
    ]
}
let payload: [String: Any] = [
    "engine": "macOS Vision VNRecognizeTextRequest",
    "vision_revision": request.revision,
    "lines": lines,
]
FileHandle.standardOutput.write(try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]))
