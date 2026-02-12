import Foundation

/// HTTP methods supported by the API client.
public enum JukeHTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
    case put = "PUT"
    case delete = "DELETE"
}
