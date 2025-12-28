from collections import Counter
from models.card import Card, Rank, Suit

def showdown(game) -> list:
    """
    Evaluate all active players' hands and return ranked winners.
    
    Args:
        game: PokerState object with players and community cards
        
    Returns:
        List of (player, hand_rank, hand_name) tuples, sorted from best to worst
    """
    # Get all players who haven't folded
    active_players = [p for p in game.players if not p.folded]
    
    if len(active_players) == 0:
        raise ValueError("No active players for showdown")
    
    # Evaluate each player's hand
    player_results = []
    for player in active_players:
        # Combine player's hole cards with community cards
        full_hand = player.hand + game.community_cards
        hand_rank = evaluate_hand(full_hand)
        player_results.append((player, hand_rank, hand_name(hand_rank)))
    
    # Sort by hand rank (best first)
    player_results.sort(key=lambda x: x[1], reverse=True)
    
    return player_results


def award_pot(game, ranked_results: list):
    """
    Award the pot to the winner(s) based on showdown results.
    Handles split pots for ties.
    
    Args:
        game: PokerState object
        ranked_results: Output from showdown() function
    """
    if not ranked_results:
        raise ValueError("No players to award pot to")
    
    # Find all players with the best hand (in case of tie)
    best_hand_rank = ranked_results[0][1]
    winners = [result for result in ranked_results if result[1] == best_hand_rank]
    
    # Calculate pot share
    pot_total = game.pot.total()
    pot_share = pot_total // len(winners)
    remainder = pot_total % len(winners)
    
    # Award chips to winners
    for i, (player, hand_rank, hand_name_str) in enumerate(winners):
        amount = pot_share + (1 if i < remainder else 0)
        game.pot.transfer_to(player.chips, amount)
        print(f"{player.name} wins ${amount} with {hand_name_str}")
    
    return [player for player, _, _ in winners]

def evaluate_hand(cards: list[Card]) -> tuple:
    """
    Evaluate the best 5-card poker hand from given cards.
    Returns a tuple for comparison where higher is better.
    
    Returns: (hand_type, *tiebreakers)
    Hand types: 9=Straight Flush, 8=Four of a Kind, 7=Full House, 
                6=Flush, 5=Straight, 4=Three of a Kind, 3=Two Pair, 
                2=One Pair, 1=High Card
    """
    if len(cards) < 5:
        raise ValueError("Need at least 5 cards to evaluate")
    
    # Get all possible 5-card combinations and find the best
    from itertools import combinations
    best_hand = None
    
    for five_cards in combinations(cards, 5):
        hand_value = _evaluate_five_cards(list(five_cards))
        if best_hand is None or hand_value > best_hand:
            best_hand = hand_value
    
    return best_hand


def _evaluate_five_cards(cards: list[Card]) -> tuple:
    """Evaluate exactly 5 cards and return their rank."""
    ranks = sorted([card.rank.value for card in cards], reverse=True)
    suits = [card.suit for card in cards]
    rank_counts = Counter(ranks)
    
    is_flush = len(set(suits)) == 1
    is_straight = _is_straight(ranks)
    
    # Count rank frequencies
    counts = sorted(rank_counts.values(), reverse=True)
    unique_ranks = sorted(rank_counts.keys(), key=lambda r: (rank_counts[r], r), reverse=True)
    
    # Straight Flush
    if is_straight and is_flush:
        return (9, max(ranks))
    
    # Four of a Kind
    if counts == [4, 1]:
        four_kind = [r for r, c in rank_counts.items() if c == 4][0]
        kicker = [r for r, c in rank_counts.items() if c == 1][0]
        return (8, four_kind, kicker)
    
    # Full House
    if counts == [3, 2]:
        three_kind = [r for r, c in rank_counts.items() if c == 3][0]
        pair = [r for r, c in rank_counts.items() if c == 2][0]
        return (7, three_kind, pair)
    
    # Flush
    if is_flush:
        return (6, *ranks)
    
    # Straight
    if is_straight:
        return (5, max(ranks))
    
    # Three of a Kind
    if counts == [3, 1, 1]:
        three_kind = [r for r, c in rank_counts.items() if c == 3][0]
        kickers = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
        return (4, three_kind, *kickers)
    
    # Two Pair
    if counts == [2, 2, 1]:
        pairs = sorted([r for r, c in rank_counts.items() if c == 2], reverse=True)
        kicker = [r for r, c in rank_counts.items() if c == 1][0]
        return (3, pairs[0], pairs[1], kicker)
    
    # One Pair
    if counts == [2, 1, 1, 1]:
        pair = [r for r, c in rank_counts.items() if c == 2][0]
        kickers = sorted([r for r, c in rank_counts.items() if c == 1], reverse=True)
        return (2, pair, *kickers)
    
    # High Card
    return (1, *ranks)


def _is_straight(ranks: list[int]) -> bool:
    """Check if ranks form a straight."""
    ranks_sorted = sorted(ranks)
    
    # Check regular straight
    if ranks_sorted == list(range(ranks_sorted[0], ranks_sorted[0] + 5)):
        return True
    
    # Check for A-2-3-4-5 (wheel) straight
    if ranks_sorted == [2, 3, 4, 5, 14]:
        return True
    
    return False


def hand_name(hand_rank: tuple) -> str:
    """Convert hand rank tuple to readable name."""
    hand_type = hand_rank[0]
    
    names = {
        9: "Straight Flush",
        8: "Four of a Kind",
        7: "Full House",
        6: "Flush",
        5: "Straight",
        4: "Three of a Kind",
        3: "Two Pair",
        2: "One Pair",
        1: "High Card"
    }
    
    return names.get(hand_type, "Unknown")


