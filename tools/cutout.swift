import Foundation
import Vision
import CoreImage
import CoreImage.CIFilterBuiltins

let args = CommandLine.arguments
guard args.count == 3 else {
    print("usage: swift cutout.swift <input> <output.png>")
    exit(1)
}

let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
guard let image = CIImage(contentsOf: input) else { print("cannot read input"); exit(1) }

let request = VNGenerateForegroundInstanceMaskRequest()
let handler = VNImageRequestHandler(ciImage: image)
try handler.perform([request])
guard let result = request.results?.first else { print("no subject found"); exit(1) }

let maskBuffer = try result.generateScaledMaskForImage(forInstances: result.allInstances, from: handler)
var mask = CIImage(cvPixelBuffer: maskBuffer)

// Erode then feather the matte to drop the colour fringe from the original backdrop.
let erode = CIFilter.morphologyMinimum()
erode.inputImage = mask
erode.radius = 2.5
let feather = CIFilter.gaussianBlur()
feather.inputImage = erode.outputImage!.clampedToExtent()
feather.radius = 1.2
mask = feather.outputImage!.cropped(to: image.extent)

let blend = CIFilter.blendWithMask()
blend.inputImage = image
blend.backgroundImage = CIImage.empty()
blend.maskImage = mask
let masked = blend.outputImage!.cropped(to: image.extent)
let ctx = CIContext()
try ctx.writePNGRepresentation(of: masked, to: output, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
print("wrote \(output.path)")
