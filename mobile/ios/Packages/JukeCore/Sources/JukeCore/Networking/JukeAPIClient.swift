import Foundation
import OSLog

/// HTTP client for making requests to the Juke API.
///
/// Handles URL construction, authentication headers, JSON encoding/decoding,
/// and error extraction from responses.
///
/// ## Usage
///
/// ```swift
/// let client = JukeAPIClient.shared
///
/// // GET request
/// let profile: MusicProfile = try await client.send("/api/v1/music-profiles/me/", token: token)
///
/// // POST request with body
/// let body = try JSONEncoder().encode(loginRequest)
/// let response: TokenResponse = try await client.send("/api/v1/auth/api-auth-token/", method: .post, body: body)
/// ```
public final class JukeAPIClient: @unchecked Sendable {
    /// Shared singleton instance.
    public static let shared = JukeAPIClient()

    private let configuration: JukeAPIConfiguration
    private let session: URLSession
    private let jsonDecoder: JSONDecoder
    private let logger: Logger

    /// Creates an API client with the given configuration.
    /// - Parameters:
    ///   - configuration: API configuration. Defaults to `.shared`.
    ///   - session: URL session for requests. Defaults to `.shared`.
    ///   - loggerSubsystem: Logger subsystem identifier. Defaults to "com.embario.JukeCore".
    public init(
        configuration: JukeAPIConfiguration = .shared,
        session: URLSession = .shared,
        loggerSubsystem: String = "com.embario.JukeCore"
    ) {
        self.configuration = configuration
        self.session = session
        self.jsonDecoder = JukeDateParsing.makeDecoder()
        self.logger = Logger(subsystem: loggerSubsystem, category: "APIClient")
    }

    /// The base URL for API requests.
    public var baseURL: URL {
        configuration.baseURL
    }

    /// The frontend URL for web fallback.
    public var frontendURL: URL? {
        configuration.frontendURL
    }

    // MARK: - Generic Request Methods

    /// Sends a request and decodes the response.
    /// - Parameters:
    ///   - path: API path (e.g., "/api/v1/auth/api-auth-token/").
    ///   - method: HTTP method. Defaults to `.get`.
    ///   - token: Authorization token. Optional.
    ///   - queryItems: URL query parameters. Optional.
    ///   - body: Request body data. Optional.
    /// - Returns: Decoded response of type `T`.
    /// - Throws: `JukeAPIError` on failure.
    public func send<T: Decodable>(
        _ path: String,
        method: JukeHTTPMethod = .get,
        token: String? = nil,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil
    ) async throws -> T {
        let urlRequest = try buildRequest(
            path: path,
            method: method,
            token: token,
            queryItems: queryItems,
            body: body
        )

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw JukeAPIError.networkError(error.localizedDescription)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw JukeAPIError.invalidResponse
        }

        if httpResponse.statusCode == 401 {
            throw JukeAPIError.unauthorized
        }

        guard 200..<300 ~= httpResponse.statusCode else {
            let serverMessage = extractErrorMessage(
                from: data,
                defaultMessage: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode)
            )
            throw JukeAPIError.server(status: httpResponse.statusCode, message: serverMessage)
        }

        // Handle empty responses by providing an empty JSON object
        let payload = data.isEmpty ? Data("{}".utf8) : data

        do {
            return try jsonDecoder.decode(T.self, from: payload)
        } catch {
            logDecodingError(error, path: path, data: payload)
            throw JukeAPIError.decoding(error.localizedDescription)
        }
    }

    /// Sends a request that expects no response body.
    /// - Parameters:
    ///   - path: API path.
    ///   - method: HTTP method. Defaults to `.post`.
    ///   - token: Authorization token. Optional.
    ///   - queryItems: URL query parameters. Optional.
    ///   - body: Request body data. Optional.
    /// - Throws: `JukeAPIError` on failure.
    public func sendEmpty(
        _ path: String,
        method: JukeHTTPMethod = .post,
        token: String? = nil,
        queryItems: [URLQueryItem]? = nil,
        body: Data? = nil
    ) async throws {
        let urlRequest = try buildRequest(
            path: path,
            method: method,
            token: token,
            queryItems: queryItems,
            body: body
        )

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: urlRequest)
        } catch {
            throw JukeAPIError.networkError(error.localizedDescription)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw JukeAPIError.invalidResponse
        }

        if httpResponse.statusCode == 401 {
            throw JukeAPIError.unauthorized
        }

        guard 200..<300 ~= httpResponse.statusCode else {
            let serverMessage = extractErrorMessage(
                from: data,
                defaultMessage: HTTPURLResponse.localizedString(forStatusCode: httpResponse.statusCode)
            )
            throw JukeAPIError.server(status: httpResponse.statusCode, message: serverMessage)
        }
    }

    // MARK: - Typed Convenience Methods

    /// Performs a GET request.
    public func get<T: Decodable>(
        _ path: String,
        token: String? = nil,
        queryItems: [URLQueryItem]? = nil
    ) async throws -> T {
        try await send(path, method: .get, token: token, queryItems: queryItems)
    }

    /// Performs a POST request with an encodable body.
    public func post<T: Decodable>(
        _ path: String,
        body: Encodable? = nil,
        token: String? = nil
    ) async throws -> T {
        let bodyData = try body.map { try JSONEncoder.snakeCase.encode(AnyEncodable($0)) }
        return try await send(path, method: .post, token: token, body: bodyData)
    }

    /// Performs a POST request with no expected response.
    public func postEmpty(
        _ path: String,
        body: Encodable? = nil,
        token: String? = nil
    ) async throws {
        let bodyData = try body.map { try JSONEncoder.snakeCase.encode(AnyEncodable($0)) }
        try await sendEmpty(path, method: .post, token: token, body: bodyData)
    }

    /// Performs a PATCH request with an encodable body.
    public func patch<T: Decodable>(
        _ path: String,
        body: Encodable? = nil,
        token: String? = nil
    ) async throws -> T {
        let bodyData = try body.map { try JSONEncoder.snakeCase.encode(AnyEncodable($0)) }
        return try await send(path, method: .patch, token: token, body: bodyData)
    }

    /// Performs a DELETE request.
    public func delete(_ path: String, token: String? = nil) async throws {
        try await sendEmpty(path, method: .delete, token: token)
    }

    // MARK: - Request Building

    private func buildRequest(
        path: String,
        method: JukeHTTPMethod,
        token: String?,
        queryItems: [URLQueryItem]?,
        body: Data?
    ) throws -> URLRequest {
        guard var components = URLComponents(url: configuration.baseURL, resolvingAgainstBaseURL: true) else {
            throw JukeAPIError.invalidURL
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
            throw JukeAPIError.invalidURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method.rawValue
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.timeoutInterval = 30

        if let token {
            request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        }

        return request
    }

    // MARK: - Error Extraction

    private func extractErrorMessage(from data: Data, defaultMessage: String) -> String {
        guard !data.isEmpty else {
            return defaultMessage
        }

        if let jsonObject = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
            // Check for "detail" field (Django REST Framework standard)
            if let detail = jsonObject["detail"] as? String, !detail.isEmpty {
                return detail
            }
            // Check for "non_field_errors" array
            if let nonFieldErrors = jsonObject["non_field_errors"] as? [String], let first = nonFieldErrors.first {
                return first
            }
            // Check for first field error
            if let firstValue = jsonObject.values.first as? [String], let first = firstValue.first {
                return first
            }
        }

        // Try plain text, but skip HTML responses
        if let message = String(data: data, encoding: .utf8), !message.isEmpty {
            let trimmed = message.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if trimmed.hasPrefix("<!doctype") || trimmed.hasPrefix("<html") {
                return defaultMessage
            }
            return message
        }

        return defaultMessage
    }

    // MARK: - Logging

    private func logDecodingError(_ error: Error, path: String, data: Data) {
        if let debugBody = String(data: data, encoding: .utf8) {
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
    }
}

// MARK: - Helpers

/// Type-erased encodable wrapper for encoding generic Encodable values.
private struct AnyEncodable: Encodable {
    private let value: Encodable

    init(_ value: Encodable) {
        self.value = value
    }

    func encode(to encoder: Encoder) throws {
        try value.encode(to: encoder)
    }
}

extension JSONEncoder {
    /// A JSONEncoder configured with snake_case key encoding.
    static let snakeCase: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }()
}
