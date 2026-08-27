"""Tests for the AquaSync simulation core.

These are mostly *physics* tests rather than unit tests: they assert that the
models conserve mass, respect thermodynamic and hydraulic limits, and behave
monotonically where physics says they must. A hydrological model that passes
its unit tests but does not conserve water is worse than no model, because it
is wrong in a way that looks right.
"""

from __future__ import annotations

import numpy as np
import pytest

from aquasync.twin import (
    IDAMALAYAR,
    IDUKKI,
    REACHES,
    RULE_CURVE_2020,
    HydropowerModel,
    LevelStorageCurve,
    MuskingumReach,
    ReservoirModel,
    ReservoirState,
    TidePredictor,
    UnitHydrograph,
    scs_effective_rainfall,
)
from aquasync.twin.optimizer import (
    DrawdownPolicy,
    ObjectiveWeights,
    OperationalLimits,
    ReleaseOptimizer,
)

# --------------------------------------------------------------------------
# level - storage curve
# --------------------------------------------------------------------------

class TestLevelStorageCurve:
    def test_round_trip(self):
        c = LevelStorageCurve(IDUKKI)
        for level in (700.0, 715.0, 728.5, 732.43):
            back = c.level_from_storage(c.storage_from_level(level))
            assert back == pytest.approx(level, abs=1e-6)

    def test_anchors_at_frl(self):
        c = LevelStorageCurve(IDUKKI)
        assert c.storage_from_level(IDUKKI.frl) == pytest.approx(
            IDUKKI.live_storage_at_frl, rel=1e-9
        )

    def test_dead_level_is_zero_live_storage(self):
        c = LevelStorageCurve(IDUKKI)
        assert c.storage_from_level(IDUKKI.dead_level) == pytest.approx(0.0, abs=1e-9)

    def test_monotonic(self):
        c = LevelStorageCurve(IDUKKI)
        levels = np.linspace(IDUKKI.dead_level, IDUKKI.frl, 200)
        storages = np.array([c.storage_from_level(v) for v in levels])
        assert np.all(np.diff(storages) > 0)

    def test_surface_area_is_the_storage_derivative(self):
        """area(h) must equal dS/dh, or evaporation and rain-on-lake are wrong."""
        c = LevelStorageCurve(IDUKKI)
        h, eps = 720.0, 1e-4
        numeric = (c.storage_from_level(h + eps) - c.storage_from_level(h - eps)) / (2 * eps)
        assert c.surface_area_km2(h) == pytest.approx(numeric, rel=1e-4)

    def test_fit_recovers_a_known_beta(self):
        true_beta = 1.42
        c = LevelStorageCurve(IDUKKI, beta=true_beta)
        levels = np.linspace(700.0, IDUKKI.frl, 60)
        storages = np.array([c.storage_from_level(v) for v in levels])

        fitted = LevelStorageCurve(IDUKKI, beta=1.0)
        assert fitted.fit_from_observations(levels, storages) == pytest.approx(true_beta, rel=1e-6)

    def test_fit_rejects_insufficient_data(self):
        with pytest.raises(ValueError, match="at least 3"):
            LevelStorageCurve(IDUKKI).fit_from_observations([720.0], [500.0])


# --------------------------------------------------------------------------
# reservoir mass balance
# --------------------------------------------------------------------------

class TestReservoirModel:
    def test_conserves_mass(self):
        """Storage change must equal net volume in, to numerical precision."""
        m = ReservoirModel(IDUKKI)
        start = ReservoirState(725.0, m.curve.storage_from_level(725.0))
        n = 240
        inflow = np.full(n, 300.0)
        turbine = np.full(n, 100.0)
        spill = np.zeros(n)

        states = m.simulate(start, inflow, turbine, spill, evaporation_mm_day=0.0)
        expected = start.storage + (300.0 - 100.0) * n * 3600.0 / 1e6
        assert states[-1].storage == pytest.approx(expected, rel=1e-9)

    def test_euler_step_size_is_adequate(self):
        """Hourly vs 6-minute integration must agree far inside gauge error."""
        m = ReservoirModel(IDUKKI)
        start = ReservoirState(725.0, m.curve.storage_from_level(725.0))

        coarse = m.simulate(start, np.full(72, 400.0), np.full(72, 120.0),
                            np.zeros(72), dt_seconds=3600.0, evaporation_mm_day=0.0)
        fine = m.simulate(start, np.full(720, 400.0), np.full(720, 120.0),
                          np.zeros(720), dt_seconds=360.0, evaporation_mm_day=0.0)

        # Gauge resolution is ~0.01 m; require an order of magnitude better.
        assert abs(coarse[-1].level - fine[-1].level) < 0.001

    def test_storage_never_negative(self):
        m = ReservoirModel(IDUKKI)
        start = ReservoirState(700.0, m.curve.storage_from_level(700.0))
        states = m.simulate(start, np.zeros(500), np.full(500, 500.0), np.zeros(500))
        assert all(s.storage >= 0.0 for s in states)

    def test_evaporation_lowers_level(self):
        m = ReservoirModel(IDUKKI)
        start = ReservoirState(725.0, m.curve.storage_from_level(725.0))
        dry = m.simulate(start, np.zeros(48), np.zeros(48), np.zeros(48), evaporation_mm_day=8.0)
        none = m.simulate(start, np.zeros(48), np.zeros(48), np.zeros(48), evaporation_mm_day=0.0)
        assert dry[-1].level < none[-1].level

    def test_no_spill_below_crest(self):
        """Head is measured above the SPILLWAY CREST, not an alert level.

        This test previously asserted no spill below ``red_level`` and so
        encoded the bug it should have caught: red_level is a KSDMA alert
        threshold at 728.19 m, while Idukki's chute spillway crest is
        723.29 m. Measuring head from the alert level understated discharge
        capacity roughly threefold.
        """
        m = ReservoirModel(IDUKKI)
        assert m.spill_capacity(IDUKKI.spillway_crest - 0.01, gates_open=5) == 0.0
        assert m.spill_capacity(IDUKKI.spillway_crest + 2.0, gates_open=5) > 0.0

    def test_spill_capacity_matches_design_discharge(self):
        """At FRL, the weir relation should land near the official figure.

        CAG Appendix 3.1 gives Idukki a design discharge of 5,012 cumec. A
        simple broad-crested weir formula will not match exactly - design
        discharge is normally quoted at MWL, and the real structure is a
        gated chute - but being within about 20% is the check that catches a
        wrong crest or wrong gate geometry.
        """
        q = ReservoirModel(IDUKKI).spill_capacity(IDUKKI.frl, gates_open=IDUKKI.n_gates)
        assert 0.7 * IDUKKI.design_discharge_cumecs <= q <= 1.1 * IDUKKI.design_discharge_cumecs

    def test_crest_is_not_an_alert_level(self):
        """Regression guard: the crest must never be re-set to an alert band."""
        for res in (IDUKKI, IDAMALAYAR):
            assert res.spillway_crest < res.blue_level
            assert res.spillway_crest not in (res.red_level, res.orange_level, res.blue_level)

    def test_spill_capacity_grows_with_head_and_gates(self):
        m = ReservoirModel(IDUKKI)
        low = m.spill_capacity(IDUKKI.red_level + 1.0, gates_open=2)
        high = m.spill_capacity(IDUKKI.red_level + 3.0, gates_open=2)
        more = m.spill_capacity(IDUKKI.red_level + 1.0, gates_open=4)
        assert high > low and more > low

    def test_time_to_frl(self):
        m = ReservoirModel(IDUKKI)
        s = ReservoirState(730.0, m.curve.storage_from_level(730.0))
        assert m.time_to_frl(s, 0.0) == float("inf")
        assert m.time_to_frl(s, -50.0) == float("inf")
        assert 0 < m.time_to_frl(s, 500.0) < 500


# --------------------------------------------------------------------------
# rainfall - runoff
# --------------------------------------------------------------------------

class TestRunoff:
    def test_no_runoff_below_initial_abstraction(self):
        assert scs_effective_rainfall(1.0, curve_number=72.0) == pytest.approx(0.0)

    def test_runoff_never_exceeds_rainfall(self):
        for rain in (5.0, 50.0, 200.0, 500.0):
            for cn in (55.0, 72.0, 95.0):
                assert 0.0 <= scs_effective_rainfall(rain, cn) <= rain

    def test_higher_curve_number_yields_more_runoff(self):
        assert scs_effective_rainfall(100.0, 90.0) > scs_effective_rainfall(100.0, 60.0)

    def test_unit_hydrograph_conserves_volume(self):
        """1 mm of effective rain over A km2 must integrate to A * 1000 m3."""
        uh = UnitHydrograph(time_to_peak_h=6.0)
        q = uh.ordinates(dt_hours=1.0, area_km2=649.0)
        volume = q.sum() * 3600.0
        assert volume == pytest.approx(649.0 * 1e3, rel=0.02)

    def test_steeper_catchment_peaks_sooner(self):
        steep = UnitHydrograph.from_catchment(649.0, 40.0, slope=0.08)
        flat = UnitHydrograph.from_catchment(649.0, 40.0, slope=0.005)
        assert steep.time_to_peak_h < flat.time_to_peak_h


# --------------------------------------------------------------------------
# routing
# --------------------------------------------------------------------------

class TestMuskingum:
    def test_coefficients_sum_to_one(self):
        """C0+C1+C2 = 1 is what makes the scheme conserve volume."""
        for k, x in ((8.0, 0.2), (12.0, 0.35), (4.0, 0.1)):
            c0, c1, c2 = MuskingumReach(k, x, 1.0).coefficients
            assert c0 + c1 + c2 == pytest.approx(1.0)

    def test_auto_subreaching_restores_stability(self):
        """A long reach at dt=1h is unstable until it is subdivided."""
        r = MuskingumReach(k_hours=8.0, x=0.2, dt_hours=1.0)
        assert r.n_sub > 1
        assert r.is_stable

    def test_conserves_volume(self):
        r = MuskingumReach(8.0, 0.2, 1.0)
        inflow = np.concatenate([np.full(10, 50.0), np.full(30, 600.0), np.full(200, 50.0)])
        out = r.route(inflow)
        assert out.sum() == pytest.approx(inflow.sum(), rel=0.02)

    def test_attenuates_and_lags(self):
        r = MuskingumReach(8.0, 0.2, 1.0)
        inflow = np.concatenate([np.full(5, 50.0), np.full(10, 800.0), np.full(150, 50.0)])
        out = r.route(inflow)
        assert out.max() < inflow.max()                       # attenuation
        assert int(np.argmax(out)) > int(np.argmax(inflow))   # lag

    def test_never_negative(self):
        r = MuskingumReach(11.0, 0.25, 1.0)
        inflow = np.concatenate([np.zeros(5), np.full(3, 1500.0), np.zeros(120)])
        assert np.all(r.route(inflow) >= 0.0)

    def test_rejects_invalid_x(self):
        with pytest.raises(ValueError, match=r"\[0, 0.5\]"):
            MuskingumReach(8.0, 0.7, 1.0)

    def test_calibration_recovers_known_parameters(self):
        truth = MuskingumReach(6.0, 0.25, 1.0, n_subreaches=1)
        inflow = np.concatenate([np.full(6, 60.0), np.full(24, 700.0), np.full(180, 60.0)])
        outflow = truth.route(inflow)
        k, x, r2 = MuskingumReach.calibrate(inflow, outflow, dt_hours=1.0)
        assert r2 > 0.98
        assert k == pytest.approx(6.0, rel=0.15)


# --------------------------------------------------------------------------
# tide
# --------------------------------------------------------------------------

class TestTide:
    def test_dominant_period_is_semidiurnal(self):
        """Cochin is mixed semi-diurnal: M2 should dominate the spectrum.

        Note this must be tested spectrally, not by autocorrelation. The
        autocorrelation of a *mixed* tide peaks near 24.8 h, where the
        semi-diurnal and diurnal constituents realign - which is correct
        behaviour, not a semi-diurnal signal.
        """
        a = TidePredictor().level(np.arange(0, 240, 0.1))
        freqs = np.fft.rfftfreq(len(a), d=0.1)
        power = np.abs(np.fft.rfft(a - a.mean()))
        power[0] = 0.0
        dominant_period_h = 1.0 / freqs[int(np.argmax(power))]
        assert 11.0 < dominant_period_h < 14.0

    def test_roughly_two_high_waters_per_day(self):
        a = TidePredictor().level(np.arange(0, 240, 0.1))
        highs = np.sum((a[1:-1] > a[:-2]) & (a[1:-1] > a[2:]))
        assert 1.6 <= highs / 10.0 <= 2.2

    def test_spring_range_is_realistic_for_cochin(self):
        """Cochin is microtidal; a range near 1 m is the sanity check."""
        assert 0.6 < TidePredictor().spring_range() < 1.6

    def test_finds_low_tide_windows(self):
        w = TidePredictor().low_tide_windows(horizon_hours=72)
        assert len(w) >= 3
        assert all(0 <= a < b <= 72 for a, b in w)

    def test_higher_discharge_shortens_tidal_intrusion(self):
        from aquasync.twin import TidalBackwaterModel

        m = TidalBackwaterModel()
        assert m.intrusion_length_km(2000.0) < m.intrusion_length_km(50.0)

    def test_high_tide_reduces_safe_conveyance(self):
        from aquasync.twin import TidalBackwaterModel

        m = TidalBackwaterModel()
        high = m.effective_conveyance(1100.0, 0.5, 8.0)
        low = m.effective_conveyance(1100.0, -0.5, 8.0)
        assert float(high[0]) < float(low[0])


# --------------------------------------------------------------------------
# hydropower
# --------------------------------------------------------------------------

class TestHydropower:
    @pytest.mark.parametrize("res", [IDUKKI, IDAMALAYAR])
    def test_power_is_within_range_of_nameplate(self, res):
        """Rated flow at FRL should land near installed capacity."""
        p = float(HydropowerModel(res).power_mw(res.turbine_rated_flow, res.frl)[0])
        assert 0.85 * res.installed_capacity_mw <= p <= 1.10 * res.installed_capacity_mw

    def test_no_output_below_cut_in(self):
        assert float(HydropowerModel(IDUKKI).power_mw(1.0, 730.0)[0]) == pytest.approx(0.0)

    def test_efficiency_never_exceeds_peak(self):
        m = HydropowerModel(IDUKKI)
        q = np.linspace(0, IDUKKI.turbine_rated_flow * 1.2, 60)
        assert np.all(m.turbine_efficiency(q, 650.0) <= IDUKKI.turbine_efficiency + 1e-9)

    def test_higher_level_gives_more_power(self):
        m = HydropowerModel(IDUKKI)
        assert float(m.power_mw(100.0, 730.0)[0]) > float(m.power_mw(100.0, 710.0)[0])

    def test_peak_tariff_is_worth_more(self):
        m = HydropowerModel(IDUKKI)
        peak = float(m.revenue_inr(100.0, 730.0, 19.0)[0])
        off = float(m.revenue_inr(100.0, 730.0, 3.0)[0])
        assert peak > off

    def test_spill_above_turbine_rating_is_not_charged_as_lost_revenue(self):
        """Water the turbines could never have taken is not a flood-decision cost."""
        m = HydropowerModel(IDUKKI)
        at_rating = float(m.spill_opportunity_cost(IDUKKI.turbine_rated_flow, 730.0, 12.0)[0])
        far_above = float(m.spill_opportunity_cost(IDUKKI.turbine_rated_flow * 5, 730.0, 12.0)[0])
        assert far_above == pytest.approx(at_rating)


# --------------------------------------------------------------------------
# optimiser
# --------------------------------------------------------------------------

class TestOptimizer:
    @staticmethod
    def _setup(level: float = 728.8):
        opt = ReleaseOptimizer(
            IDUKKI, REACHES["periyar_lower"],
            weights=ObjectiveWeights.monsoon_peak(),
            limits=OperationalLimits(max_release_cumecs=1200.0,
                                     max_ramp_cumecs_per_hour=60.0),
            seed=1,
        )
        state = ReservoirState(level, opt.curve.storage_from_level(level))
        return opt, state

    def test_evaluation_respects_release_bounds(self):
        opt, state = self._setup()
        ev = opt.evaluate(np.full(72, 9999.0), state, np.full(72, 200.0))
        assert np.all(ev.release <= opt.limits.max_release_cumecs + 1e-9)

    def test_policy_respects_ramp_limit(self):
        opt, state = self._setup()
        rel = opt.policy_schedule(state, np.full(120, 400.0),
                                  DrawdownPolicy(728.0, start_hour=0, max_rate=1200.0))
        ramp = np.abs(np.diff(rel))
        assert ramp.max() <= opt.limits.max_ramp_cumecs_per_hour + 1e-6

    def test_policy_draws_down_toward_target(self):
        opt, state = self._setup(level=731.0)
        rel = opt.policy_schedule(state, np.full(400, 150.0),
                                  DrawdownPolicy(728.5, start_hour=0, max_rate=900.0))
        ev = opt.evaluate(rel, state, np.full(400, 150.0))
        assert ev.levels[-1] < 731.0
        assert ev.levels[-1] == pytest.approx(728.5, abs=0.6)

    def test_policy_search_is_deterministic(self):
        """The grid is exhaustive, so two runs must agree exactly."""
        inflow = np.concatenate([np.full(48, 150.0), np.full(24, 800.0), np.full(96, 200.0)])
        a, pa = self._setup()[0].search_policies(self._setup()[1], inflow)
        b, pb = self._setup()[0].search_policies(self._setup()[1], inflow)
        assert a.total_cost == pytest.approx(b.total_cost)
        assert (pa.target_level, pa.start_hour, pa.max_rate) == (
            pb.target_level, pb.start_hour, pb.max_rate
        )

    def test_optimised_beats_the_baseline(self):
        opt, state = self._setup(level=729.5)
        inflow = np.concatenate([np.full(48, 150.0), np.full(24, 900.0), np.full(120, 250.0)])
        result = opt.compare(state, inflow)
        assert result["optimised"].total_cost <= result["baseline"].total_cost

    def test_grid_offtake_cap_reduces_revenue(self):
        """Energy the grid will not take must not be booked as revenue."""
        inflow = np.full(200, 600.0)
        release = np.full(200, 600.0)

        uncapped, state = self._setup()
        a = uncapped.evaluate(release, state, inflow)

        capped = ReleaseOptimizer(
            IDUKKI, REACHES["periyar_lower"],
            limits=OperationalLimits(max_release_cumecs=1200.0,
                                     max_mean_turbine_cumecs=50.0),
            seed=1,
        )
        b = capped.evaluate(release, state, inflow)
        assert b.revenue_inr < a.revenue_inr

    def test_policy_describes_itself(self):
        text = DrawdownPolicy(728.5, 118, 480.0).describe("Idukki")
        assert "728.50" in text and "480" in text and "118" in text


# --------------------------------------------------------------------------
# constants, against the published record
# --------------------------------------------------------------------------

class TestPublishedConstants:
    """Guards against the four constant defects the research sweep found.

    Every figure here is traceable to CAG Appendix 3.1 or 3.3 in
    research/sources/papers/CAG_Kerala_flood_audit.pdf, cross-checked against
    the live KSEB monthly workbook.
    """

    @pytest.mark.parametrize("res", [IDUKKI, IDAMALAYAR])
    def test_mwl_is_above_frl(self, res):
        """MWL equal to FRL models zero surcharge - it hid ~90 MCM at Idukki."""
        assert res.mwl > res.frl
        assert res.surcharge_range > 0.5

    def test_published_mwl_values(self):
        assert IDUKKI.mwl == pytest.approx(734.11)
        assert IDAMALAYAR.mwl == pytest.approx(171.20)

    @pytest.mark.parametrize("res", [IDUKKI, IDAMALAYAR])
    def test_rule_curve_is_monotonic_through_the_monsoon(self, res):
        """The curve refills the reservoir as the monsoon recedes."""
        levels = [lv for _, _, lv in RULE_CURVE_2020[res.key]]
        # strict=False is correct here: levels[1:] is deliberately one shorter.
        assert all(b >= a for a, b in zip(levels, levels[1:], strict=False))
        assert levels[-1] <= res.frl

    @pytest.mark.parametrize("res", [IDUKKI, IDAMALAYAR])
    def test_rule_curve_is_a_step_function(self, res):
        """KSEB holds the end-of-period value across each ten-day step."""
        # 01 and 10 July must give the same level; 11 July must not.
        assert res.rule_level_on(7, 1) == res.rule_level_on(7, 10)
        assert res.rule_level_on(7, 11) != res.rule_level_on(7, 10)

    def test_rule_curve_matches_kseb_workbook(self):
        """Spot values KSEB published independently of CAG."""
        assert IDUKKI.rule_level_on(7, 10) == pytest.approx(724.00)   # 2375.33 ft
        assert IDUKKI.rule_level_on(7, 20) == pytest.approx(724.80)   # 2377.95 ft
        assert IDUKKI.rule_level_on(7, 31) == pytest.approx(725.60)   # 2380.58 ft
        assert IDUKKI.rule_level_on(8, 15) == pytest.approx(727.50)   # 2386.81 ft

    def test_scalar_rule_level_is_the_end_of_august_row(self):
        for res in (IDUKKI, IDAMALAYAR):
            assert res.rule_level == pytest.approx(res.rule_level_on(8, 31))

    def test_alert_bands_are_offsets_below_the_rule_level(self):
        """Idamalayar blue and orange previously fired 1.0 m and 0.5 m late."""
        blue, orange, red = IDAMALAYAR.alert_levels_on(8, 31)
        assert (blue, orange, red) == pytest.approx((162.50, 163.00, 163.50))
        assert (IDAMALAYAR.blue_level, IDAMALAYAR.orange_level, IDAMALAYAR.red_level) \
            == pytest.approx((162.50, 163.00, 163.50))

    def test_idukki_alert_offsets_are_in_feet(self):
        blue, orange, red = IDUKKI.alert_levels_on(8, 31)
        assert (blue, orange, red) == pytest.approx((726.06, 727.89, 728.19), abs=0.01)

    def test_alert_bands_move_with_the_season(self):
        """A frozen scalar would give the same band in June and October."""
        assert IDUKKI.alert_levels_on(6, 15) != IDUKKI.alert_levels_on(10, 15)

    def test_routing_matches_the_cwc_published_travel_time(self):
        """CWC's December-2018 report: 8 h Idukki to Neeleeswaram.

        The previous geometry estimates summed to 19 h - about 2x too slow,
        which would make the twin recommend acting far too late.
        """
        total_k = REACHES["periyar_upper"].k_hours + REACHES["periyar_lower"].k_hours
        assert total_k == pytest.approx(8.0, abs=0.5)
