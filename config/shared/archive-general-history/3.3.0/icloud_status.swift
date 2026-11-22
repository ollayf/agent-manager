// Usage: swift icloud_status.swift status|evict <file>...
// Prints one line per file: "<state>\t<path>", state in uploaded | uploading | not-uploaded | evicted | not-icloud | error:<msg>
import Foundation

let args = CommandLine.arguments
guard args.count >= 3, ["status", "evict"].contains(args[1]) else {
    FileHandle.standardError.write("usage: icloud_status.swift status|evict <file>...\n".data(using: .utf8)!)
    exit(64)
}
let keys: Set<URLResourceKey> = [.isUbiquitousItemKey, .ubiquitousItemIsUploadedKey, .ubiquitousItemIsUploadingKey,
                                 .ubiquitousItemDownloadingStatusKey]
for path in args[2...] {
    let url = URL(fileURLWithPath: path)
    do {
        let v = try url.resourceValues(forKeys: keys)
        guard v.isUbiquitousItem == true else { print("not-icloud\t\(path)"); continue }
        let uploaded = v.ubiquitousItemIsUploaded == true
        if args[1] == "evict" {
            if !uploaded { print("not-uploaded\t\(path)"); continue }
            try FileManager.default.evictUbiquitousItem(at: url)
            print("evicted\t\(path)")
        } else if uploaded {
            print(v.ubiquitousItemDownloadingStatus == .current ? "uploaded\t\(path)" : "evicted\t\(path)")
        } else {
            print((v.ubiquitousItemIsUploading == true ? "uploading" : "not-uploaded") + "\t\(path)")
        }
    } catch {
        print("error:\(error.localizedDescription)\t\(path)")
    }
}
