/** 塔罗（domain=tarot）的 chart_facts 形状。 */

export interface TarotCard {
  position: string
  card_id: string
  name: string
  name_cn: string
  suit: 'major' | 'wands' | 'cups' | 'swords' | 'pentacles'
  number: number | null
  element: string
  orientation: 'upright' | 'reversed'
  orientation_cn: string
  keywords: string[]
}

export interface TarotFacts {
  spread: { id: string; name: string; positions: string[]; card_count: number }
  deck: { mode: 'all' | 'major' | 'minor'; pool_size: number; used: string }
  draw: {
    seed: string
    auto_seed: boolean
    allow_reversed: boolean
    reversed_probability: number
    replacement: boolean
  }
  cards: TarotCard[]
}
