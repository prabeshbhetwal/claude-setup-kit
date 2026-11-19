// model-pilot's settings: what the plugin options mean to the pilot. Pure.
import type { Register } from 'claude-code'

export type Options = {
  privacy: boolean
  privateFolders: string
  allowUpgrade: boolean
  /** 'auto', '250k', '500k', '750k' or 'never'. */
  handoff: string
  /** Try Jev before Haiku when its CLI and key are there. */
  useJev: boolean
  /** The longest the first model request waits for the judge. */
  judgeBudgetMs: number
  /** The model that judges: an alias or an id. */
  judgeModel: string
  /** Judge and log, but leave every request as the menu has it. */
  isShadow: boolean
  /** Ask before a turn the pilot (not the person) would run on Fable. */
  confirmFable: boolean
}

/** The settings as the pilot reads them; anything missing or malformed takes its default. */
export function optionsOf(options: Parameters<Register>[1]): Options {
  return {
    privacy: options.privacy === true,
    privateFolders: typeof options.privateFolders === 'string' ? options.privateFolders : '',
    allowUpgrade: options.allowUpgrade !== false,
    handoff: typeof options.handoff === 'string' ? options.handoff : 'auto',
    useJev: options.jev === true, // opt-in: Jev sends prompt text to a third party
    judgeBudgetMs: typeof options.judgeBudgetMs === 'number' && options.judgeBudgetMs > 0 ? options.judgeBudgetMs : 2500,
    judgeModel: typeof options.judgeModel === 'string' && options.judgeModel.trim() ? options.judgeModel.trim() : 'haiku',
    isShadow: options.shadow === true,
    confirmFable: options.confirmFable !== false,
  }
}

/** The judges this setup tries, in order. */
export const chainOf = (o: Options): readonly ('jev' | 'haiku')[] => (o.useJev ? ['jev', 'haiku'] : ['haiku'])
