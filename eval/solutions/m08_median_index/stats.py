def get_median(numbers):
    if not numbers:
        return None
    sorted_nums = sorted(numbers)
    n = len(sorted_nums)
    return sorted_nums[n // 2]
