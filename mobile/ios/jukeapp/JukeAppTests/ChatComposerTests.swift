import Testing
@testable import JukeApp

struct ChatComposerTests {
    @Test func testBlankDraft_SendIsDisabled() {
        for draft in ["", " ", "\n\t "] {
            #expect(!ChatComposer.canSend(draft: draft, isSending: false))
        }
    }

    @Test func testNonblankAndMultilineDraft_SendIsEnabled() {
        for draft in ["Why this song?", " First line\nSecond line "] {
            #expect(ChatComposer.canSend(draft: draft, isSending: false))
        }
    }

    @Test func testRequestInFlight_SendIsDisabledUntilCompletion() {
        #expect(!ChatComposer.canSend(draft: "Another question", isSending: true))
        #expect(ChatComposer.canSend(draft: "Another question", isSending: false))
    }
}
