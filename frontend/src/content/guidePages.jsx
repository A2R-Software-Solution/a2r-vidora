import SiteLink from "../components/common/SiteLink";

const tryVidora = <SiteLink href="/">Try it on a video you have permission to process</SiteLink>;

export const guidePages = {
  "/guides": {
    label: "Guides",
    eyebrow: "Guides",
    title: "Practical guides for learning from video.",
    description: "Guides on summarizing long videos, finding exact moments, studying from lectures, and asking better questions of a video.",
    intro: "Long videos are full of useful ideas and hard to skim. These guides explain techniques for getting value from them, with or without Vidora AI.",
    sections: [
      { id: "all-guides", title: "Browse the guides", content: <>
        <ul>
          <li><SiteLink href="/guides/summarize-long-videos">How to summarize a long video without losing the point</SiteLink> — a method for pulling out structure, claims, and evidence.</li>
          <li><SiteLink href="/guides/find-exact-moments-in-videos">How to find an exact moment in a video</SiteLink> — searching by idea instead of scrubbing the timeline.</li>
          <li><SiteLink href="/guides/study-from-lecture-videos">Studying from lecture videos</SiteLink> — turning a two-hour recording into review material.</li>
          <li><SiteLink href="/guides/ask-better-questions">Asking better questions of a video</SiteLink> — what makes a question answerable from a transcript.</li>
          <li><SiteLink href="/faq">Frequently asked questions</SiteLink> — limits, accuracy, privacy, and supported sources.</li>
        </ul>
      </> },
      { id: "about-guides", title: "About these guides", content: <>
        <p>The guides are written by the {`Vidora AI`} team and describe general techniques. They are not a substitute for watching a video when accuracy matters, and they do not assume any particular video or creator.</p>
        <p>Want to see the workflow described here in practice? Read <SiteLink href="/how-it-works">how Vidora works</SiteLink>.</p>
      </> },
    ],
  },
  "/guides/summarize-long-videos": {
    label: "Summarize long videos",
    eyebrow: "Guide",
    title: "How to summarize a long video without losing the point.",
    description: "A practical method for summarizing lectures, talks, and interviews: capture the structure, the claims, and the evidence.",
    intro: "A good summary is not a shorter transcript. It records what the video argues, how it supports that argument, and what you should do with it.",
    sections: [
      { id: "start-with-purpose", title: "Start with why you are watching", content: <>
        <p>The same one-hour talk supports many different summaries. A student preparing for an exam needs definitions and worked examples. A manager deciding whether to share it needs the main recommendation and its caveats. Write down your purpose before you begin; it decides what to keep.</p>
        <p>If you are evaluating a video, look for the speaker’s thesis in the first few minutes and the conclusion at the end. Most talks state both, even when the middle wanders.</p>
      </> },
      { id: "capture-structure", title: "Capture the structure first", content: <>
        <p>Before details, list the major sections in order: the problem, the approach, each main point, and the conclusion. Three to seven headings is typical for an hour of content. This skeleton makes the rest much easier to place.</p>
        <p>Then add one sentence per section. If you cannot summarize a section in one sentence, you probably have not yet understood its main idea, which is a signal to revisit that part of the video.</p>
      </> },
      { id: "separate-claims-and-evidence", title: "Separate claims from evidence", content: <>
        <p>Speakers often mix a claim, an example, and a story in a single minute. Mark which is which. A claim is what the speaker wants you to believe. Evidence is the data, example, or reasoning offered in support. Stories illustrate, but rarely prove.</p>
        <p>Record the strongest piece of evidence for each claim, along with its timestamp so you can check it later. A summary with timestamps is verifiable; one without them asks you to trust your own memory.</p>
      </> },
      { id: "using-ai", title: "Where AI summaries help, and where they do not", content: <>
        <p>An AI summary can produce a first outline quickly, which is useful when you are deciding whether a video is worth an hour. It can also miss context, mishear names or numbers, and flatten a nuanced argument into a confident sentence.</p>
        <p>Treat the output as a draft. Check figures, quotations, and anything you plan to repeat against the original. {tryVidora}, then read the summary alongside the timestamps it links to.</p>
      </> },
    ],
  },
  "/guides/find-exact-moments-in-videos": {
    label: "Find exact moments",
    eyebrow: "Guide",
    title: "How to find an exact moment in a video.",
    description: "Stop scrubbing the timeline. Learn how to locate a specific idea in a long video by searching for what was said.",
    intro: "You remember that someone explained it clearly, somewhere around the middle. Finding it by dragging the progress bar is slow. Searching by meaning is faster.",
    sections: [
      { id: "why-scrubbing-fails", title: "Why scrubbing the timeline fails", content: <>
        <p>A progress bar tells you where you are in time, not what is being discussed. In a long lecture, ten minutes of similar-looking content can hide the one explanation you need, so you end up sampling a few seconds at a time and guessing.</p>
        <p>Chapters help when the creator provides them, but many videos have none, and chapter titles are often too broad to identify a specific point.</p>
      </> },
      { id: "search-by-idea", title: "Search by the idea, not the exact words", content: <>
        <p>You rarely remember the speaker’s exact phrasing. Describe the idea instead: “the part where they compare the two approaches” or “the reason given for delaying the launch.” Transcript-based tools match on the spoken content, so distinctive terms, names, and topics work best.</p>
        <p>If your first attempt returns nothing useful, rephrase using a different key term. Speakers often use a synonym you would not have chosen.</p>
      </> },
      { id: "verify-the-timestamp", title: "Always verify the timestamp", content: <>
        <p>Jump to the returned moment and listen for a few seconds before and after. Check that the passage really says what the answer claims, and that you are not seeing a nearby but different point.</p>
        <p>If a video contains crucial information shown only on screen, such as a slide, chart, or demo, a transcript will not capture it. In that case use the timestamp as a starting point, then watch the section.</p>
      </> },
      { id: "keep-a-list", title: "Keep a list of useful moments", content: <>
        <p>When you find a good moment, write down the timestamp and a note about why it matters. A short list of moments is a reusable index of the video, which saves you from repeating the search later.</p>
        <p>{tryVidora} and use its timestamp links to jump straight to each answer.</p>
      </> },
    ],
  },
  "/guides/study-from-lecture-videos": {
    label: "Study from lectures",
    eyebrow: "Guide",
    title: "Studying from lecture videos.",
    description: "How to turn long lecture recordings into effective review material using outlines, questions, and spaced review.",
    intro: "Watching a recording from start to finish feels productive, but passive viewing is a weak way to learn. Active techniques work much better.",
    sections: [
      { id: "before-you-watch", title: "Prepare before you press play", content: <>
        <p>Skim the course syllabus or the slides for the lecture, and write two or three questions you expect it to answer. Knowing what to look for makes it easier to notice the important parts and to recall them later.</p>
        <p>Watch in blocks of 20 to 30 minutes and pause between them. Attention drops in long sessions, and short breaks improve retention.</p>
      </> },
      { id: "build-an-outline", title: "Build an outline as you go", content: <>
        <p>Write the topic of each section, with a timestamp. Include definitions in your own words, and note any example the lecturer works through. Timestamps let you return to a difficult derivation without rewatching everything.</p>
        <p>Flag anything you did not understand. Those flags become your list of questions for office hours, a study group, or a second viewing.</p>
      </> },
      { id: "test-yourself", title: "Test yourself instead of rereading", content: <>
        <p>After the lecture, close your notes and try to explain the main ideas aloud or on paper. Then check what you missed. Retrieval practice like this consistently outperforms rereading and rewatching.</p>
        <p>Turn each flagged confusion into a specific question, such as “Why does the second step require the first assumption?” Specific questions can be answered and checked, unlike “explain this lecture.”</p>
      </> },
      { id: "review-on-a-schedule", title: "Review on a schedule", content: <>
        <p>Revisit your outline the next day, then after a few days, then after a week. Spacing your reviews helps knowledge move into long-term memory.</p>
        <p>Use an AI assistant only as a study aid. It can help you locate where a topic was covered and rephrase an explanation, but it can make mistakes, especially with formulas and specialist vocabulary. Check them against the lecture and your course materials. Read our <SiteLink href="/guides/ask-better-questions">guide to asking better questions</SiteLink> next.</p>
      </> },
    ],
  },
  "/guides/ask-better-questions": {
    label: "Ask better questions",
    eyebrow: "Guide",
    title: "Asking better questions of a video.",
    description: "What makes a question answerable from a video transcript, with examples of weak questions and stronger rewrites.",
    intro: "The quality of an answer depends heavily on the question. A precise question points to a specific passage; a vague one gets a vague reply.",
    sections: [
      { id: "one-idea", title: "Ask about one idea at a time", content: <>
        <p>“What is this video about and what did they say about costs and who was the guest?” contains three questions. Split them. Each one can then be matched to a different part of the video and checked separately.</p>
        <p>Start broad to get oriented, then narrow. A follow-up such as “What reasons are given for that decision?” works best after you know which decision is being discussed.</p>
      </> },
      { id: "be-specific", title: "Be specific about what you want", content: <>
        <table>
          <thead><tr><th>Weak question</th><th>Stronger question</th></tr></thead>
          <tbody>
            <tr><td>Tell me everything.</td><td>What are the three main recommendations, in order?</td></tr>
            <tr><td>Is this good?</td><td>What evidence does the speaker give for the claim that costs fall?</td></tr>
            <tr><td>What about the budget?</td><td>How does the speaker say the budget changed from last year?</td></tr>
          </tbody>
        </table>
      </> },
      { id: "answerable-from-speech", title: "Ask what the speech can answer", content: <>
        <p>A transcript contains what was said. Questions about the speaker’s tone, about what appeared on a slide, or about facts the video never mentions cannot be answered reliably from it. If the answer depends on something visual, watch that section.</p>
        <p>Likewise, opinion questions such as “Is the speaker right?” need your own judgement. Ask instead what reasons and evidence the speaker offers, then evaluate them yourself.</p>
      </> },
      { id: "check-the-answer", title: "Check the answer against the source", content: <>
        <p>Even a good answer can contain a mistake, particularly with numbers, names, and quotations. Follow the timestamp, listen to the passage, and confirm. If the answer and the video disagree, trust the video.</p>
        <p>{tryVidora} and practice with a talk you know well, so you can judge how the answers compare to what you remember.</p>
      </> },
    ],
  },
  "/faq": {
    label: "FAQ",
    eyebrow: "FAQ",
    title: "Frequently asked questions.",
    description: "Answers about Vidora AI: supported videos, length limits, accuracy, privacy, and how long analyses are kept.",
    intro: "Quick answers to the things people ask most. If yours is not here, contact the team.",
    sections: [
      { id: "what-is-vidora", title: "What is Vidora AI?", content: <>
        <p>Vidora AI is a tool that turns the spoken content of a supported YouTube video into a searchable conversation. You can read a summary, ask questions, and follow timestamp links to the moment in the video that supports each answer. See <SiteLink href="/about">About</SiteLink> for more.</p>
      </> },
      { id: "supported-videos", title: "Which videos are supported?", content: <>
        <p>The current beta supports public YouTube videos. Private, unavailable, live, and upcoming videos may not work. Other sources are not available yet, even where the interface mentions them as planned.</p>
      </> },
      { id: "limits", title: "How long can a video be?", content: <>
        <p>Guests can analyze videos up to 35 minutes. Signed-in users can analyze videos up to 3 hours. Processing time depends on the video length and current service demand.</p>
      </> },
      { id: "accuracy", title: "How accurate are the answers?", content: <>
        <p>Speech recognition and AI answers can contain errors, especially with names, numbers, accents, background music, or specialist terms. Always verify important information against the video using the timestamp links. Read our <SiteLink href="/guides/ask-better-questions">guide to asking better questions</SiteLink> for tips.</p>
      </> },
      { id: "data", title: "What happens to my data?", content: <>
        <p>Audio is processed temporarily and analyses expire and are cleaned up periodically. The <SiteLink href="/privacy">Privacy Policy</SiteLink> lists what is collected, which providers process it, and how to request access or deletion.</p>
      </> },
      { id: "rights", title: "Do I need permission to analyze a video?", content: <>
        <p>Submit only videos you own or have permission to process, and follow the source platform’s terms. Vidora is not affiliated with or endorsed by YouTube or Google. See the <SiteLink href="/terms">Terms of Use</SiteLink> for details.</p>
      </> },
      { id: "help", title: "Who do I contact for help?", content: <>
        <p>Use the <SiteLink href="/contact">Contact page</SiteLink> for support, feedback, privacy requests, or content concerns.</p>
      </> },
    ],
  },
};
