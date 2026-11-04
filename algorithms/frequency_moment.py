"""
Algorithm k-FrequencyMoment: the k-th frequency moment of a multiset in 2 MapReduce rounds

The k-th frequency moment of a string x of length n over the alphabet Sigma is
    f_k(x) = sum over symbols s in Sigma of |{i in [n]: x_i = s}|^k.
That is, for every symbol s in the alphabet, we count the number of times it is repeated in x,
raise it to the power k, and then take the sum of these raised numbers.

The input to the MapReduce model is a set of <key; value> pairs, so we think of x as n pairs
where the i-th pair corresponds to the symbol x_i and is represented as <i; x_i>.
"""

from typing import Iterable, Tuple
from pyspark import RDD

# The special symbol $: the key every pair gets in the second round
DOLLAR = "$"


# =============================================================================
# ROUND 1: MAPPER mu_1 AND REDUCER rho_1
# =============================================================================

def mapper_1(pair: Tuple[int, str]) -> Tuple[str, int]:
    """
    Mapper mu_1
    Input: a pair <i; x_i>
    We replace the pair by the new pair where the symbol is the key, and the position is the value.
    That is, mu_1(<i; x_i>) = <x_i; i>
    Emit: <x_i; i>
    """
    i, x_i = pair
    return (x_i, i)


def reducer_1(pair: Tuple[str, Iterable[int]], k: int) -> Tuple[str, int]:
    """
    Reducer rho_1
    Input: the input to each reducer will be a unique string symbol, and the list of positions in which
    this symbol appears. That is, <x_i; {v_1, ..., v_m}>
    Compute the k-th frequency moment of the symbol x_i using rho_1(<x_i; {v_1, ..., v_m}>) = <x_i; m^k>
    Emit: <x_i; m^k>
    """
    x_i, positions = pair
    m = len(list(positions))
    return (x_i, m ** k)


# =============================================================================
# ROUND 2: MAPPER mu_2 AND REDUCER rho_2
# =============================================================================

def mapper_2(pair: Tuple[str, int]) -> Tuple[str, int]:
    """
    Mapper mu_2
    Input: <x_i; v>
    We would like to sum the numbers computed using the reducer rho_1.
    We map each pair to have the same key. That is, mu_2(<x_i; v>) = <$; v>
    Emit: <$; v>
    """
    x_i, v = pair
    return (DOLLAR, v)


def reducer_2(pair: Tuple[str, Iterable[int]]) -> Tuple[str, int]:
    """
    Reducer rho_2
    Input: all pairs have the same key and were sent to the same reducer. The input is <$; {v_1, ..., v_l}>
    Sum the pairs using rho_2(<$; {v_1, ..., v_l}>) = <$; sum_{i=1}^{l} v_i>
    Emit: <$; sum_{i=1}^{l} v_i>
    """
    dollar, values = pair
    return (dollar, sum(values))


# =============================================================================
# ALGORITHM k-FREQUENCYMOMENT
# =============================================================================

def k_frequency_moment(pairs: RDD, k: int) -> int:
    """
    Algorithm k-FrequencyMoment
    Input: a string x of length n where the i-th symbol in this string is denoted by x_i,
    given as the n pairs <i; x_i> (an RDD spread over the machines).
    Output: the k-th frequency moment of x, f_k(x) = sum over symbols s in Sigma of |{i in [n]: x_i = s}|^k.

    Each round is a map followed by a shuffle that sends all pairs with the same key to one reducer
    (groupByKey), so the reducer gets the whole list of values, as in the algorithm.
    """
    # Round 1: mu_1 then rho_1, one reducer per symbol of the alphabet
    round_1 = pairs.map(mapper_1) \
        .groupByKey() \
        .map(lambda pair: reducer_1(pair, k))

    # Round 2: mu_2 then rho_2, a single reducer for the key $
    round_2 = round_1.map(mapper_2) \
        .groupByKey() \
        .map(reducer_2)

    [(dollar, f_k)] = round_2.collect()
    return f_k
