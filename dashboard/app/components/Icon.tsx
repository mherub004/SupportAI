const paths = {
  assistant: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3Z",
  inbox: "M4 4h16v16H4V4Zm0 10h5l2 3h2l2-3h5",
  book: "M12 5v15M3 4h5l4 2 4-2h5v15h-5l-4 2-4-2H3V4Z",
  handoff: "M4 19 19 4M8 4h11v11",
  clock: "M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z",
  settings: "M4 7h16M4 17h16M8 4v6m8 4v6",
  mail: "M3 5h18v14H3V5Zm0 0 9 8 9-8",
  check: "m5 12 4 4L19 6",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z",
} as const;
export type IconName = keyof typeof paths;
export default function Icon({ name }: { name: IconName }) {
  return <svg className="ui-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
