import Foundation
import OSLog

struct APIConfiguration {
    static let shared = APIConfiguration()

    let baseURL: URL

    init(bundle: Bundle = .main, processInfo: ProcessInfo = .processInfo) {
        let plistValue = bundle.object(forInfoDictionaryKey: "BACKEND_URL") as? String
        self.init(environment: processInfo.environment, plistValue: plistValue)
    }

    init(environment: [String: String], plistValue: String?) {
        if let overrideURLString = environment["BACKEND_URL"], let url = URL(string: overrideURLString) {
            baseURL = url
            return
        }

        if let plistValue, let url = URL(string: plistValue) {
            baseURL = url
            return
        }

        fatalError("BACKEND_URL must be set in the environment or Info.plist.")
    }
}

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case patch = "PATCH"
    case put = "PUT"
}

enum APIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case server(status: Int, message: String)
    case decoding(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Could not build API request."
        case .invalidResponse:
            return "Received an invalid response from the server."
        case .server(_, let message):
            return message
        case .decoding:
            return "Unable to parse server response."
        }
    }
}

final class APIClient {
    static let shared = APIClient()
    private static let iso8601WithFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
    private static let iso8601WithoutFractionalSeconds: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter
    }()
    private static let iso8601Microseconds: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSSZ"
        return formatter
    }()
    private static let iso8601MicrosecondsZone: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .iso8601)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyy-MM-dd'T'HH:mm:ss.SSSSSSXXXXX"
        return formatter
    }()

    private let configuration: APIConfiguration
    private let session: URLSession
    private let jsonDecoder: JSONDecoder
    private let logger = Logger(subsystem: "com.embario.juke", category: "APIClient")

    init(configuration: APIConfiguration = .shared, session: URLSession = .shared) {
        self.configuration = configuration
        self.session = session
        self.jsonDecoder = JSONDecoder()
        self.jsonDecoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let value = try container.decode(String.self)
            if let date = APIClient.iso8601WithFractionalSeconds.date(from: value) {
                return date
            }
            if let date = APIClient.iso8601WithoutFractionalSeconds.date(from: value) {
                return date
            }
            if let date = APIClient.iso8601Microseconds.date(from: value) {
                return date
            }
            if let date = APIClient.iso8601MicrosecondsZone.date(from: value) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Invalid ISO8601 date: \(value)"
            )
        }
    }

    func send<T: Decodable>(
        _ path: String,
        method: HTTPMethod = .get,
        token: String? = nil,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil
    ) async throws -> T {
        let urlRequest = try buildRequest(path: path, method: method, token: token, queryItems: queryItems, body: body)
        let (data, response) = try await session.data(for: urlRequest)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }

        guard 200..<300 ~= httpResponse.statusCode else {
            let serverMessage = extractErrorMessage(from: data, defaultMessage: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode))
            throw APIError.server(status: httpResponse.statusCode, message: serverMessage)
        }

        let payload = data.isEmpty ? Data("{}".utf8) : data

        do {
            return try jsonDecoder.decode(T.self, from: payload)
        } catch {
            if let debugBody = String(data: payload, encoding: .utf8) {
                logger.error("Failed to decode response for path: \(path, privacy: .public). Raw body: \(debugBody, privacy: .public). Error: \(error.localizedDescription, privacy: .public)")
            } else {
                logger.error("Failed to decode response for path: \(path, privacy: .public). Raw body was not UTF-8 decodable. Error: \(error.localizedDescription, privacy: .public)")
            }

            switch error {
            case let DecodingError.dataCorrupted(context):
                logger.error("Decoding data corrupted: \(context.debugDescription, privacy: .public) CodingPath: \(context.codingPath.map { $0.stringValue }.joined(separator: "."), privacy: .public)")
            case let DecodingError.keyNotFound(key, context):
                logger.error("Decoding key not found: \(key.stringValue, privacy: .public) Context: \(context.debugDescription, privacy: .public) CodingPath: \(context.codingPath.map { $0.stringValue }.joined(separator: "."), privacy: .public)")
            case let DecodingError.typeMismatch(type, context):
                logger.error("Decoding type mismatch for \(String(describing: type), privacy: .public). Context: \(context.debugDescription, privacy: .public) CodingPath: \(context.codingPath.map { $0.stringValue }.joined(separator: "."), privacy: .public)")
            case let DecodingError.valueNotFound(type, context):
                logger.error("Decoding value not found for \(String(describing: type), privacy: .public). Context: \(context.debugDescription, privacy: .public) CodingPath: \(context.codingPath.map { $0.stringValue }.joined(separator: "."), privacy: .public)")
            default:
                break
            }

            throw APIError.decoding(error)
        }
    }

    private func buildRequest(
        path: String,
        method: HTTPMethod,
        token: String?,
        queryItems: [URLQueryItem]?,
        body: Data?
    ) throws -> URLRequest {
        guard var components = URLComponents(url: configuration.baseURL, resolvingAgainstBaseURL: true) else {
            throw APIError.invalidURL
        }

        let preserveTrailingSlash = path.hasSuffix("/")
        let isAbsolutePath = path.hasPrefix("/")

        var normalizedPath = path
        if normalizedPath.hasPrefix("/") {
            normalizedPath.removeFirst()
        }
        if preserveTrailingSlash, normalizedPath.hasSuffix("/") {
            normalizedPath.removeLast()
        }

        var combinedPath = isAbsolutePath ? "/" : configuration.baseURL.path
        if !combinedPath.hasSuffix("/") {
            combinedPath += "/"
        }
        if !normalizedPath.isEmpty {
            combinedPath += normalizedPath
        }
        if preserveTrailingSlash, !combinedPath.hasSuffix("/") {
            combinedPath += "/"
        }
        components.path = combinedPath
        if let queryItems, !queryItems.isEmpty {
            components.queryItems = queryItems
        }

        guard let url = components.url else {
            throw APIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token {
            request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    private func extractErrorMessage(from data: Data, defaultMessage: String) -> String {
        guard !data.isEmpty else {
            return defaultMessage
        }

        if let jsonObject = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            if let detail = jsonObject["detail"] as? String, !detail.isEmpty {
                return detail
            }
            if let nonFieldErrors = jsonObject["non_field_errors"] as? [String], let first = nonFieldErrors.first {
                return first
            }
        }

        if let message = String(data: data, encoding: .utf8), !message.isEmpty {
            let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if trimmed.hasPrefix("<!doctype") || trimmed.hasPrefix("<html") {
                return defaultMessage
            }
            return message
        }

        return defaultMessage
    }
}
