"""Compare out-of-sample model predictions with the betting market on the same bouts.

Odds are converted to implied probabilities and the bookmaker margin is removed proportionally.
This is evaluation only: market numbers never flow back into features, training or inference.
There is deliberately no betting-return analysis; FightLens is not a tipping product.
"""

from dataclasses import dataclass

import numpy as np

from app.ml.evaluate import BacktestResult, calibration_table, winner_metrics
from app.ml.features import METHOD_CLASSES
from app.ml.models import EPS

PROP_KEYS = ("ko", "sub", "dec")  # aligned with METHOD_CLASSES


@dataclass(frozen=True)
class MarketLine:
    f1_moneyline: float
    f2_moneyline: float
    props: tuple[float | None, ...]  # f1 ko, sub, dec, f2 ko, sub, dec


def implied(american: float) -> float:
    """Raw implied probability of American odds (includes the bookmaker margin)."""
    return 100 / (american + 100) if american > 0 else -american / (-american + 100)


def market_p_f1(line: MarketLine) -> tuple[float, float]:
    """(margin-free P(fighter 1 wins), overround)."""
    p1, p2 = implied(line.f1_moneyline), implied(line.f2_moneyline)
    return p1 / (p1 + p2), p1 + p2 - 1


def market_six(line: MarketLine) -> np.ndarray | None:
    """Margin-free six-outcome distribution from method props, or None if any prop is missing."""
    if any(v is None for v in line.props):
        return None
    raw = np.array([implied(v) for v in line.props])
    return raw / raw.sum()


def compare_to_market(
    bt: BacktestResult,
    lines: dict[int, MarketLine],
    truth: dict[int, tuple[bool, str | None, int]],  # (fighter 1 won, method, year)
    selected_winner: str,
    selected_method: str,
) -> dict:
    """Metrics for market vs. every model on the bouts where both have a prediction."""
    ids = sorted(set(bt.bout_p_f1[selected_winner]) & set(lines))
    if not ids:
        return {"n": 0}
    y = np.array([1.0 if truth[i][0] else 0.0 for i in ids])
    market = np.array([market_p_f1(lines[i])[0] for i in ids])
    overround = float(np.mean([market_p_f1(lines[i])[1] for i in ids]))

    winner = {"market": winner_metrics(market, y)}
    for kind, preds in bt.bout_p_f1.items():
        winner[kind] = winner_metrics(np.array([preds[i] for i in ids]), y)
    winner["coin_flip"] = winner_metrics(np.full(len(ids), 0.5), y)
    model = np.array([bt.bout_p_f1[selected_winner][i] for i in ids])

    years = sorted({truth[i][2] for i in ids})
    out = {
        "n": len(ids),
        "years": years,
        "mean_overround": overround,
        "winner": winner,
        "favourite_agreement": float(np.mean((market > 0.5) == (model > 0.5))),
        "mean_abs_gap": float(np.mean(np.abs(market - model))),
        "market_calibration": calibration_table(market, y),
    }

    # Six-outcome comparison where all props exist and the method is one we model.
    six_ids = [i for i in ids if market_six(lines[i]) is not None and truth[i][1] in METHOD_CLASSES]
    if six_ids and selected_method in bt.bout_methods:
        market_ll, model_ll = [], []
        for i in six_ids:
            f1_won, method = truth[i][0], truth[i][1]
            idx = (0 if f1_won else 3) + METHOD_CLASSES.index(method)
            market_ll.append(-np.log(max(market_six(lines[i])[idx], EPS)))
            p1 = bt.bout_p_f1[selected_winner][i]
            d1, d2 = bt.bout_methods[selected_method][i]
            model_six = np.concatenate([p1 * d1, (1 - p1) * d2])
            model_ll.append(-np.log(max(model_six[idx], EPS)))
        out["six_outcome"] = {
            "n": len(six_ids),
            "market_log_loss": float(np.mean(market_ll)),
            "model_log_loss": float(np.mean(model_ll)),
        }
    return out


def lines_from_rows(rows) -> dict[int, MarketLine]:
    return {
        r.bout_id: MarketLine(
            r.f1_moneyline,
            r.f2_moneyline,
            tuple(getattr(r, f"{side}_{k}") for side in ("f1", "f2") for k in PROP_KEYS),
        )
        for r in rows
    }


def render_section(cmp: dict, selected_winner: str) -> list[str]:
    if not cmp.get("n"):
        return [
            "## Benchmark: betting market",
            "",
            "No bookmaker odds imported (`fightlens import-odds`), so there's no market comparison.",
            "",
        ]
    w = cmp["winner"]
    lines = [
        "## Benchmark: betting market (evaluation only, never a model input)",
        "",
        f"{cmp['n']} backtest bouts with moneylines from the Ultimate UFC Dataset (the source "
        "doesn't document when the lines were taken). "
        f"The bookmaker margin (mean overround {cmp['mean_overround']:.1%}) is removed proportionally. "
        "Every row below is scored on exactly the same bouts.",
        "",
        "| Predictor | Log loss | Brier | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for kind in [
        "market",
        selected_winner,
        *[k for k in w if k not in ("market", selected_winner)],
    ]:
        m = w[kind]
        label = f"{kind} **(selected model)**" if kind == selected_winner else kind
        lines.append(f"| {label} | {m['log_loss']:.4f} | {m['brier']:.4f} | {m['accuracy']:.1%} |")
    gap = w[selected_winner]["log_loss"] - w["market"]["log_loss"]
    lines += [
        "",
        f"- Market minus model log loss: {-gap:+.4f}. "
        + (
            "The market is sharper, as expected: it prices in information the model doesn't have (camp news, injuries, styles)."
            if gap > 0
            else "The model matches or beats the market on this subset."
        ),
        f"- The model and the market pick the same favourite in {cmp['favourite_agreement']:.1%} of bouts. "
        f"Mean absolute probability gap: {cmp['mean_abs_gap']:.1%}.",
    ]
    if "six_outcome" in cmp:
        s = cmp["six_outcome"]
        lines.append(
            f"- Six outcomes (winner × method), {s['n']} bouts with full method props: market log loss "
            f"{s['market_log_loss']:.4f}, model {s['model_log_loss']:.4f}."
        )
    lines += [
        "",
        "### Market calibration (favourite's implied probability vs. how often the favourite won)",
        "",
        "| Bucket | Bouts | Mean implied | Observed |",
        "|---|---:|---:|---:|",
        *[
            f"| {c['bucket']} | {c['n']} | {c['mean_predicted']:.1%} | {c['observed']:.1%} |"
            for c in cmp["market_calibration"]
        ],
        "",
    ]
    return lines
