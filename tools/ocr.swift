import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    print("usage: ocr.swift <image>")
    exit(1)
}
let path = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: path) else {
    print("cannot load image")
    exit(1)
}
var rect = NSRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    print("cannot convert image")
    exit(1)
}
let request = VNRecognizeTextRequest { request, error in
    if let error = error {
        print("error: \(error)")
        return
    }
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    for observation in observations {
        if let candidate = observation.topCandidates(1).first {
            print(candidate.string)
        }
    }
}
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    print("perform error: \(error)")
    exit(1)
}
