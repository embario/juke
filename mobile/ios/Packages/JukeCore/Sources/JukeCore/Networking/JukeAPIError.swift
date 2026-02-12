import Foundation

/// Errors returned by the Juke API client.
public enum JukeAPIError: LocalizedError, Equatable {
    /// The URL could not be constructed.
    case invalidURL

    /// The server response was not a valid HTTP response.
    case invalidResponse

    /// The user's session has expired (401 Unauthorized).
    case unauthorized

    /// The server returned an error status code.
    case server(status: Int, message: String)

    /// The response could not be decoded.
    case decoding(String)

    /// A network error occurred.
    case networkError(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Could not build API request."
        case .invalidResponse:
            return "Received an invalid response from the server."
        case .unauthorized:
            return "Session expired. Please log in again."
        case .server(_, let message):
            return message
        case .decoding(let details):
            return "Unable to parse server response: \(details)"
        case .networkError(let details):
            return details
        }
    }

    public static func == (lhs: JukeAPIError, rhs: JukeAPIError) -> Bool {
        switch (lhs, rhs) {
        case (.invalidURL, .invalidURL):
            return true
        case (.invalidResponse, .invalidResponse):
            return true
        case (.unauthorized, .unauthorized):
            return true
        case (.server(let lStatus, let lMessage), .server(let rStatus, let rMessage)):
            return lStatus == rStatus && lMessage == rMessage
        case (.decoding(let lDetails), .decoding(let rDetails)):
            return lDetails == rDetails
        case (.networkError(let lDetails), .networkError(let rDetails)):
            return lDetails == rDetails
        default:
            return false
        }
    }
}
