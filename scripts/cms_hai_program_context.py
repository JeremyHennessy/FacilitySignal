"""Pin CMS HAI comparison context; never compute provider scores or historical trends."""
from dataclasses import dataclass
from datetime import date
from scripts.qualify_cms_hai_benchmark import GROUPS

@dataclass(frozen=True)
class Context:
    dataset: str
    program: str
    released: str | None
    performance: tuple[str, str]
    baseline_year: int
    status: str
    provenance: str

RULE="https://www.govinfo.gov/content/pkg/FR-2025-08-04/html/2025-14681.htm"
QUALITYNET="https://qualitynet.cms.gov/inpatient/hac"
COMPARE=tuple(Context(x,"care_compare","2026-11-12",("2025-01-01","2025-12-31"),2022,
                      "observed_edition_rule_supported_baseline",RULE)
              for x in ("yd3s-jyhd","77hc-ibv8"))
HAC_FY2026=Context("yq43-i98g","hacrp","2026-05-13",("2023-01-01","2024-12-31"),2015,
                   "observed_edition_program_supported_baseline",QUALITYNET)
HAC_FY2028=Context("yq43-i98g","hacrp",None,("2025-01-01","2026-12-31"),2022,
                   "scheduled_public_early_2028_not_observed",QUALITYNET)
OBSERVED=(*COMPARE,HAC_FY2026)

def guard(left, right, left_metric, right_metric):
    """Only same-Compare-release benchmark context is allowed, not outcome attribution."""
    if left not in OBSERVED or right not in OBSERVED:
        return "unknown_or_unobserved_edition"
    if left.program!=right.program:
        return "different_reporting_programs"
    if left.baseline_year!=right.baseline_year:
        return "different_baseline"
    if left.performance!=right.performance:
        return "different_performance_period"
    if left.released!=right.released:
        return "different_source_release"
    if left_metric!=right_metric or left_metric not in GROUPS:
        return "different_or_unsupported_measure"
    if (left.dataset,right.dataset)!=("77hc-ibv8","yd3s-jyhd"):
        return "unsupported_reporting_grains"
    return "same_context_benchmark_only"

def key_compatible(program_a,baseline_a,period_a,program_b,baseline_b,period_b):
    """Structural check only, useful for rejecting inputs not admitted by guard()."""
    if any(x not in ("care_compare","hacrp") for x in (program_a,program_b)):
        return "unknown_program"
    if program_a!=program_b:
        return "different_reporting_programs"
    if baseline_a not in (2015,2022) or baseline_b not in (2015,2022):
        return "unknown_baseline"
    if baseline_a!=baseline_b:
        return "different_baseline"
    try:
        for a,b in (period_a,period_b):
            if not (date.fromisoformat(a).isoformat()==a and date.fromisoformat(b).isoformat()==b
                    and a<=b):
                return "unknown_period"
    except (TypeError,ValueError):
        return "unknown_period"
    return "same_program_baseline_and_period" if period_a==period_b else "different_performance_period"
