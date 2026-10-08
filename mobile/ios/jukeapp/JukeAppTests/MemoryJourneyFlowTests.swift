import Foundation
import ImageIO
import Testing
import UniformTypeIdentifiers
@testable import JukeApp

@Suite struct MemoryJourneyFlowTests {
    @Test func photosComeFirstUnlessMusicIsPlaying() {
        #expect(MemoryJourneyFlow().order == [.photo, .song, .story, .review])
        #expect(MemoryJourneyFlow(startWithSong: true).order == [.song, .photo, .story, .review])
    }

    @Test func stepsUnlockAsTheyAreReached() {
        var flow = MemoryJourneyFlow()
        flow.jump(to: .story)
        #expect(flow.step == .photo)
        flow.next(); flow.next()
        #expect(flow.step == .story)
        flow.back()
        #expect(flow.step == .song)
        flow.jump(to: .story)
        #expect(flow.step == .story)
        flow.jump(to: .review)
        #expect(flow.step == .story)
    }

    @Test func backStopsAtTheFirstStepAndNextAtTheReview() {
        var flow = MemoryJourneyFlow()
        flow.back()
        #expect(flow.isFirst)
        flow.next(); flow.next(); flow.next(); flow.next()
        #expect(flow.step == .review)
        flow.complete()
        #expect(flow.step == .complete && !flow.showsProgress)
    }

    @Test func buttonLabelsFollowWhatWasChosen() {
        var flow = MemoryJourneyFlow()
        #expect(flow.primaryLabel(hasPhotos: false, hasSong: false) == "Continue without photos")
        #expect(flow.primaryLabel(hasPhotos: true, hasSong: false) == "Bring these along")
        flow.next()
        #expect(flow.primaryLabel(hasPhotos: false, hasSong: false) == "Continue without a song")
        #expect(flow.primaryLabel(hasPhotos: false, hasSong: true) == "Keep going")
    }

    @Test func theMusicFirstHookAsksIfThisIsTheOne() {
        let flow = MemoryJourneyFlow(startWithSong: true)
        #expect(flow.title(draftHasSong: false, nowPlaying: true, question: "q") == "Is this the one?")
        #expect(flow.title(draftHasSong: true, nowPlaying: true, question: "q") == "What was the soundtrack?")
        #expect(MemoryJourneyFlow().title(draftHasSong: false, nowPlaying: true, question: "q") == "Find a little time machine.")
    }

    @Test func questionsUseWhatWasChosenWithoutRepeats() {
        let date = Date(timeIntervalSince1970: 1_700_000_000)
        let questions = MemoryJourneyFlow.questions(place: "Lisbon", songTitle: "Blue in Green", date: date, hasMedia: true, insightQuestion: "What comes back to you?")
        #expect(questions.first == "What were you doing in Lisbon?")
        #expect(questions.contains("Where were you when “Blue in Green” found you?"))
        #expect(questions.filter { $0 == "What comes back to you?" }.count == 1)
        #expect(MemoryJourneyFlow.question(at: 7, in: questions) == questions[7 % questions.count])
        #expect(MemoryJourneyFlow.question(at: -1, in: questions) == questions.last)
        #expect(MemoryJourneyFlow.question(at: 3, in: []) == "What comes back to you?")
    }

    @Test func aPhotosExifDateDatesTheMemory() throws {
        let data = NSMutableData()
        let destination = try #require(CGImageDestinationCreateWithData(data, UTType.jpeg.identifier as CFString, 1, nil))
        let space = CGColorSpaceCreateDeviceRGB()
        let context = try #require(CGContext(data: nil, width: 4, height: 4, bitsPerComponent: 8, bytesPerRow: 0, space: space, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        let image = try #require(context.makeImage())
        CGImageDestinationAddImage(destination, image, [kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2019:07:04 18:30:00"]] as CFDictionary)
        #expect(CGImageDestinationFinalize(destination))
        let date = try #require(MemoryJourneyFlow.captureDate(fromImageData: data as Data))
        let parts = Calendar.current.dateComponents([.year, .month, .day], from: date)
        #expect(parts.year == 2019 && parts.month == 7 && parts.day == 4)
        #expect(MemoryJourneyFlow.captureDate(fromImageData: Data([1, 2, 3])) == nil)
    }
}
