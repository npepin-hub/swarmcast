"""Sklearn WC strength model — train.csv features, persisted scaler + model."""
from __future__ import annotations

import math
from pathlib import Path

from ...config import settings
from .ml_log import research_ml_log

import joblib
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

BACKEND_DIR = Path(__file__).resolve().parents[2]
TRAIN_CSV = BACKEND_DIR / "data" / "train.csv"
ARTIFACT_PATH = BACKEND_DIR / "model_artifact.pkl"

INDEPENDENT_VARS = [
    "goals_scored_last_4y",
    "goals_received_last_4y",
    "wins_last_4y",
    "losses_last_4y",
    "draws_last_4y",
]
DEPENDENT_VAR = "winner"


def _artifact_exists() -> bool:
    return ARTIFACT_PATH.is_file()


def training(
    table_path: str | Path,
    teams: list[str],
    dependent_var: str = DEPENDENT_VAR,
    independent_vars: list[str] | None = None,
) -> dict:
    """Train linear model on train.csv subset; persist model + scaler + feature names."""
    independent_vars = independent_vars or INDEPENDENT_VARS
    df = pd.read_csv(table_path)
    df = df[df["team"].isin(teams)]
    X = df[independent_vars].fillna(0)
    y = df[dependent_var].fillna(0)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)
    model = LinearRegression()
    model.fit(X_train_s, y_train)
    y_pred = model.predict(X_test_s)
    mse = mean_squared_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    artifact = {
        "model": model,
        "scaler": scaler,
        "independent_vars": independent_vars,
        "dependent_var": dependent_var,
    }
    joblib.dump(artifact, ARTIFACT_PATH)
    return {"model_id": str(ARTIFACT_PATH), "mse": mse, "r2": r2}


def prediction(
    feature_df: pd.DataFrame,
    artifact_path: str | Path | None = None,
) -> dict:
    """Predict tournament-strength score per team row (uses persisted scaler)."""
    artifact_path = Path(artifact_path or ARTIFACT_PATH)
    artifact = joblib.load(artifact_path)
    model = artifact["model"]
    scaler = artifact["scaler"]
    independent_vars = artifact["independent_vars"]
    X = feature_df[independent_vars].fillna(0)
    request = {
        "artifact": str(artifact_path),
        "independent_vars": independent_vars,
        "teams": feature_df["team"].tolist(),
        "feature_rows": feature_df[["team", *independent_vars]].to_dict(orient="records"),
    }
    research_ml_log("prediction request", payload=request)
    X_s = scaler.transform(X)
    y_pred = model.predict(X_s)
    response = {"prediction": y_pred.tolist(), "teams": feature_df["team"].tolist()}
    research_ml_log("prediction response", payload=response)
    return response


def ensure_model(training_teams: list[str] | None = None) -> Path:
    """Train artifact if missing."""
    if _artifact_exists():
        return ARTIFACT_PATH
    df = pd.read_csv(TRAIN_CSV)
    teams = training_teams or df["team"].unique().tolist()
    training(TRAIN_CSV, teams)
    return ARTIFACT_PATH


def _strength_to_match_probs(strength_a: float, strength_b: float) -> float:
    """Map relative tournament-strength scores to P(Team A wins) this fixture."""
    diff = strength_a - strength_b
    return 1.0 / (1.0 + math.exp(-diff))


def _feature_form_score(row: dict) -> float:
    """Heuristic match form (not the WC-winner linear model). Higher = stronger."""
    return (
        float(row.get("wins_last_4y", 0))
        + 0.05 * float(row.get("goals_scored_last_4y", 0))
        - 0.05 * float(row.get("goals_received_last_4y", 0))
        - 0.5 * float(row.get("losses_last_4y", 0))
    )


def _feature_compare_prob(row_a: dict, row_b: dict) -> float:
    diff = _feature_form_score(row_a) - _feature_form_score(row_b)
    return 1.0 / (1.0 + math.exp(-diff / 10.0))


def _strength_to_goals(
    strength_a: float,
    strength_b: float,
    *,
    prob_a: float | None = None,
) -> tuple[int, int]:
    """Scoreline from strength gap and blended win probability."""
    if prob_a is not None:
        if prob_a >= 0.55:
            return 2, 1
        if prob_a <= 0.45:
            return 1, 2
    if strength_a > strength_b + 0.15:
        return 2, 1
    if strength_b > strength_a + 0.15:
        return 1, 2
    return 1, 1


def predict_match(
    team_a: str,
    team_b: str,
    feature_df: pd.DataFrame,
) -> dict:
    """
    Run model on two team rows; return match-level baseline for hybrid voting.

    feature_df must have columns: team + INDEPENDENT_VARS (two rows).
    """
    ensure_model()
    ordered = feature_df.set_index("team").reindex([team_a, team_b]).reset_index()
    ordered["team"] = [team_a, team_b]
    research_ml_log(f"predict_match team_a={team_a} team_b={team_b}")
    result = prediction(ordered)
    preds = result["prediction"]
    strength_a, strength_b = float(preds[0]), float(preds[1])
    rows = ordered.to_dict(orient="records")
    row_a, row_b = rows[0], rows[1]
    prob_tournament = _strength_to_match_probs(strength_a, strength_b)
    prob_features = _feature_compare_prob(row_a, row_b)
    w = max(0.0, min(1.0, settings.research_ml_form_weight))
    # Match forecast: lean on form (goals/wins); tournament-winner coefs are weak for fixtures
    prob_a = (1.0 - w) * prob_tournament + w * prob_features
    goals_a, goals_b = _strength_to_goals(strength_a, strength_b, prob_a=prob_a)
    model_favored = team_a if strength_a >= strength_b else team_b
    form_favored = team_a if _feature_form_score(row_a) >= _feature_form_score(row_b) else team_b
    match_out = {
        "team_a": team_a,
        "team_b": team_b,
        "team_a_strength": strength_a,
        "team_b_strength": strength_b,
        "probability_team_a_tournament": prob_tournament,
        "probability_team_a_features": prob_features,
        "probability_team_a": prob_a,
        "model_favored_team": model_favored,
        "form_favored_team": form_favored,
        "team_a_goals": goals_a,
        "team_b_goals": goals_b,
        "feature_rows": rows,
        "ml_summary": (
            f"Form ({w:.0%} weight): favors {form_favored}, P({team_a})={prob_features:.1%}. "
            f"Tournament linear model ({1-w:.0%}): favors {model_favored}, "
            f"P({team_a})={prob_tournament:.1%} (strength {strength_a:.3f} vs {strength_b:.3f}). "
            f"Match baseline P({team_a})={prob_a:.1%}, score {goals_a}-{goals_b}. "
            "Features may be train.csv fallback if MCP match stats are empty."
        ),
    }
    research_ml_log("predict_match response", payload=match_out)
    return match_out
