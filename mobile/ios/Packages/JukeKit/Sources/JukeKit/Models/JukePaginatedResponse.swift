import Foundation

/// A paginated response from the API.
public struct JukePaginatedResponse<T: Decodable>: Decodable {
    /// The results for this page.
    public let results: [T]

    /// Total count of items (if provided by the API).
    public let count: Int?

    /// URL for the next page (if available).
    public let next: String?

    /// URL for the previous page (if available).
    public let previous: String?

    public init(results: [T], count: Int? = nil, next: String? = nil, previous: String? = nil) {
        self.results = results
        self.count = count
        self.next = next
        self.previous = previous
    }
}
