"""Slug et nom des environnements éphémères (4K-286, ADR-0030 §3)."""

import re

import pytest
from shared.models import (
    EPHEMERAL_NAME_MAX,
    EPHEMERAL_SLUG_MAX,
    EphemeralSlugError,
    ephemeral_env_name,
    ephemeral_slug,
)

RFC1123 = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


@pytest.mark.parametrize("branch,expected", [
    ("feat/login", "feat-login"),
    ("Feature/Login_Page", "feature-login-page"),
    ("fix--double", "fix-double"),
    ("-leading/trailing-", "leading-trailing"),
    ("release.1.2", "release-1-2"),
])
def test_slug_normalise_la_branche(branch, expected):
    assert ephemeral_slug(branch, "my-app") == expected


def test_slug_est_conforme_rfc1123_et_sans_double_tiret():
    slug = ephemeral_slug("Feat/ÉTÉ__2026!!", "my-app")
    assert RFC1123.match(slug)
    assert "--" not in slug


def test_slug_trop_long_est_tronque_avec_suffixe_stable():
    branch = "feature/a-very-long-branch-name-for-testing"
    slug = ephemeral_slug(branch, "my-app")
    assert len(slug) <= EPHEMERAL_SLUG_MAX
    assert re.search(r"-[0-9a-f]{4}$", slug)
    assert slug == ephemeral_slug(branch, "my-app")  # déterministe


@pytest.mark.parametrize("branch", ["dev", "prod", "staging", "platform", "PROD"])
def test_slug_reserve_recoit_un_suffixe(branch):
    slug = ephemeral_slug(branch, "my-app")
    assert slug != branch.lower()
    assert slug.startswith(branch.lower() + "-")


def test_collision_avec_un_slug_pris_recoit_un_suffixe():
    taken = {"feat-x"}
    slug = ephemeral_slug("feat/x", "my-app", taken=taken)
    assert slug != "feat-x"
    assert slug.startswith("feat-x-")


def test_deux_branches_proches_ne_donnent_pas_le_meme_suffixe():
    a = ephemeral_slug("feat/x", "my-app", taken={"feat-x"})
    b = ephemeral_slug("feat_x", "my-app", taken={"feat-x"})
    assert a != b


def test_nom_complet_respecte_la_limite_helm():
    app = "a" * 40
    slug = ephemeral_slug("feature/something-long", app)
    assert len(ephemeral_env_name(app, slug)) <= EPHEMERAL_NAME_MAX


def test_nom_complet_utilise_le_double_tiret():
    assert ephemeral_env_name("my-app", "feat-login") == "my-app--feat-login"


@pytest.mark.parametrize("branch", ["", "///", "!!!"])
def test_branche_non_normalisable_est_refusee(branch):
    with pytest.raises(EphemeralSlugError):
        ephemeral_slug(branch, "my-app")


def test_app_au_slug_trop_long_pour_un_env_est_refusee():
    with pytest.raises(EphemeralSlugError):
        ephemeral_slug("feature/very-long-branch", "a" * 50)
