export type ComparePanelId = 'top' | 'bottom';

export type CompareHostMessage =
  | { type: 'ramulator-compare-load'; panel: ComparePanelId; name: string; buffer: ArrayBuffer }
  | { type: 'ramulator-compare-set-viewport'; panel: ComparePanelId; start: number; duration: number }
  | { type: 'ramulator-compare-set-cursor'; panel: ComparePanelId; time: number | null }
  | { type: 'ramulator-compare-align-mode'; panel: ComparePanelId; enabled: boolean };

export type ComparePanelMessage =
  | { type: 'ramulator-compare-ready'; panel: ComparePanelId }
  | { type: 'ramulator-compare-loaded'; panel: ComparePanelId; name: string; dramType: string; events: number }
  | { type: 'ramulator-compare-error'; panel: ComparePanelId; message: string }
  | { type: 'ramulator-compare-viewport'; panel: ComparePanelId; start: number; duration: number }
  | { type: 'ramulator-compare-cursor'; panel: ComparePanelId; time: number | null }
  | {
      type: 'ramulator-compare-anchor';
      panel: ComparePanelId;
      clk: number;
      eventId: string;
      command: string;
      address: number[];
    };

export function isCompareHostMessage(value: unknown): value is CompareHostMessage {
  if (!value || typeof value !== 'object') return false;
  return typeof (value as { type?: unknown }).type === 'string'
    && (value as { type: string }).type.startsWith('ramulator-compare-');
}
