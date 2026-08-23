from rest_framework import serializers


def validate_variant_buckets(variants_data, traffic_allocation=10000):
    """Validate that variant bucket ranges are valid for a version."""
    if not variants_data:
        return

    # Check for exactly one control
    controls = [v for v in variants_data if v.get("is_control", False)]
    if len(controls) != 1:
        raise serializers.ValidationError("Exactly one variant must be marked as control.")

    # Sort by bucket_start
    sorted_variants = sorted(variants_data, key=lambda v: v["bucket_start"])

    # Check ranges are valid
    for v in sorted_variants:
        if v["bucket_start"] > v["bucket_end"]:
            raise serializers.ValidationError(
                f"Variant '{v['key']}': bucket_start ({v['bucket_start']}) "
                f"must be <= bucket_end ({v['bucket_end']})."
            )
        if v["bucket_end"] >= traffic_allocation:
            raise serializers.ValidationError(
                f"Variant '{v['key']}': bucket_end ({v['bucket_end']}) "
                f"exceeds traffic allocation ({traffic_allocation})."
            )

    # Check no overlaps
    for i in range(len(sorted_variants) - 1):
        current = sorted_variants[i]
        next_variant = sorted_variants[i + 1]
        if current["bucket_end"] >= next_variant["bucket_start"]:
            raise serializers.ValidationError(
                f"Bucket ranges overlap between '{current['key']}' "
                f"(ends at {current['bucket_end']}) and '{next_variant['key']}' "
                f"(starts at {next_variant['bucket_start']})."
            )

    # Check contiguous coverage
    if sorted_variants[0]["bucket_start"] != 0:
        raise serializers.ValidationError("Bucket ranges must start at 0.")
    if sorted_variants[-1]["bucket_end"] != traffic_allocation - 1:
        raise serializers.ValidationError(
            f"Bucket ranges must cover up to {traffic_allocation - 1}."
        )
    for i in range(len(sorted_variants) - 1):
        if sorted_variants[i]["bucket_end"] + 1 != sorted_variants[i + 1]["bucket_start"]:
            raise serializers.ValidationError(
                f"Gap between '{sorted_variants[i]['key']}' and '{sorted_variants[i + 1]['key']}'."
            )

    # Check traffic_percentage sum
    total_percentage = sum(v["traffic_percentage"] for v in variants_data)
    if total_percentage != traffic_allocation:
        raise serializers.ValidationError(
            f"Sum of variant traffic_percentage ({total_percentage}) "
            f"must equal traffic_allocation ({traffic_allocation})."
        )
