import { Term } from '../../components/Term';
import { SCOPE_NAME, type Scope } from './macroText';

/** Quiet label saying which news days a set of findings covers. Renders nothing for no scope. */
export function ScopeLabel({ scope }: { scope: Scope | null | undefined }) {
  if (!scope) return null;
  return scope === 'excluding_earnings' ? (
    <>
      Excluding days near <Term id="earnings">earnings releases</Term>
    </>
  ) : (
    <>{SCOPE_NAME.all_events}</>
  );
}
