/** What the numbers mean and where they stop being reliable. */
export default function AboutPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 text-sm leading-relaxed text-slate-200">
      <h1 className="text-2xl font-semibold text-slate-50">About SkyLens</h1>

      <p>
        SkyLens brings together aviation occurrence reports from the United States and Canada, expresses them as rates
        rather than raw counts, and explains each one in plain English. It covers 1 July 2025 to 30 June 2026.
      </p>

      <Section title="Where the data comes from">
        <ul className="list-disc space-y-1 pl-5">
          <li><b>Transport Canada CADORS</b> — Canadian occurrence reports</li>
          <li><b>NTSB CAROL</b> — US accident and incident reports</li>
          <li><b>FAA ATADS</b> — official operation counts at 528 towered US airports</li>
          <li><b>Statistics Canada 23-10-0296</b> — official movements at 121 Canadian airports</li>
          <li><b>US Bureau of Transportation Statistics</b> — 7 million airline flights, for the flight page and as a fallback denominator</li>
          <li><b>OurAirports</b> — airport locations and identifiers</li>
        </ul>
      </Section>

      <Section title="Why rates, not counts">
        <p>
          A large airport handles more traffic, so it reports more of everything. Dividing by aircraft movements makes
          airports comparable. Where no official traffic count exists, this site shows the count and leaves the rate
          blank rather than inventing a denominator.
        </p>
      </Section>

      <Section title="What the models do, and don't">
        <ul className="list-disc space-y-1 pl-5">
          <li>
            US reports carry no category, so a classifier assigns one. Those are labelled <b>predicted</b> and stored
            with a confidence score. Canadian categories come from Transport Canada and are never overwritten.
          </li>
          <li>
            Plain-English summaries are generated from the report and passages retrieved from the FAA Pilot/Controller
            Glossary and other reference documents. The model may use only those passages, and each summary records
            which ones it used.
          </li>
          <li>
            No model runs while you use this site. Everything was computed in advance and stored in the database.
          </li>
          <li>
            Nothing here is a safety rating. A high rate means more was reported, which can reflect good reporting
            culture as much as anything else.
          </li>
        </ul>
      </Section>

      <Section title="Known limits">
        <ul className="list-disc space-y-1 pl-5">
          <li>Canadian rates include local training circuits, so busy flight-training airports read high.</li>
          <li>Only 3 of 168 fatal US accidents in the window have a published probable cause yet; final reports take a year or more. Text-based features therefore lean toward simpler, quickly closed cases.</li>
          <li>Airports with fewer than 5 occurrences have no report page, since small numbers move rates wildly.</li>
          <li>The flight page covers US domestic flights by reporting carriers only.</li>
        </ul>
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-medium text-slate-50">{title}</h2>
      {children}
    </section>
  )
}
