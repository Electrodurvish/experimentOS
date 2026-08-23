import pytest
from rest_framework import serializers

from apps.experiments.validators import validate_variant_buckets


class TestValidateVariantBuckets:
    def test_valid_two_variants(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        validate_variant_buckets(variants)  # Should not raise

    def test_valid_three_variants(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 3334,
             "bucket_start": 0, "bucket_end": 3333},
            {"key": "treatment_a", "is_control": False, "traffic_percentage": 3333,
             "bucket_start": 3334, "bucket_end": 6666},
            {"key": "treatment_b", "is_control": False, "traffic_percentage": 3333,
             "bucket_start": 6667, "bucket_end": 9999},
        ]
        validate_variant_buckets(variants)

    def test_no_control_raises(self):
        variants = [
            {"key": "a", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "b", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="control"):
            validate_variant_buckets(variants)

    def test_multiple_controls_raises(self):
        variants = [
            {"key": "a", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "b", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="control"):
            validate_variant_buckets(variants)

    def test_overlapping_ranges_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 5000},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="overlap"):
            validate_variant_buckets(variants)

    def test_gap_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4998},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="Gap"):
            validate_variant_buckets(variants)

    def test_not_starting_at_zero_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 1, "bucket_end": 5000},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5001, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="start at 0"):
            validate_variant_buckets(variants)

    def test_not_covering_full_range_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 5000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9998},
        ]
        with pytest.raises(serializers.ValidationError, match="cover up to"):
            validate_variant_buckets(variants)

    def test_invalid_start_end_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 10000,
             "bucket_start": 5000, "bucket_end": 0},
        ]
        with pytest.raises(serializers.ValidationError, match="bucket_start"):
            validate_variant_buckets(variants)

    def test_percentage_mismatch_raises(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 4000,
             "bucket_start": 0, "bucket_end": 4999},
            {"key": "treatment", "is_control": False, "traffic_percentage": 5000,
             "bucket_start": 5000, "bucket_end": 9999},
        ]
        with pytest.raises(serializers.ValidationError, match="traffic_percentage"):
            validate_variant_buckets(variants)

    def test_custom_traffic_allocation(self):
        variants = [
            {"key": "control", "is_control": True, "traffic_percentage": 2500,
             "bucket_start": 0, "bucket_end": 2499},
            {"key": "treatment", "is_control": False, "traffic_percentage": 2500,
             "bucket_start": 2500, "bucket_end": 4999},
        ]
        validate_variant_buckets(variants, traffic_allocation=5000)

    def test_empty_variants(self):
        validate_variant_buckets([])  # Should not raise
