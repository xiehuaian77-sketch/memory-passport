/**
 * Web3 EIP-1193 Browser Injected Wallet Bridge (MetaMask / Rabby / OKX / etc.)
 *
 * Provides minimal, zero-heavy-dependency primitives for:
 * - Detecting injected EVM provider (window.ethereum)
 * - Requesting accounts (eth_requestAccounts)
 * - Chain ID verification & Monad Testnet switching (10143 / 0x279F)
 * - SIWE message signing (personal_sign)
 * - Event subscription (accountsChanged, chainChanged)
 */

export const MONAD_CHAIN_ID_DECIMAL = 10143;
export const MONAD_CHAIN_ID_HEX = '0x279F';
export const MONAD_RPC_URL = 'https://testnet-rpc.monad.xyz';
export const MONAD_CHAIN_NAME = 'Monad Testnet';
export const MONAD_NATIVE_CURRENCY = {
  name: 'MON',
  symbol: 'MON',
  decimals: 18,
};
export const MONAD_EXPLORER_URL = 'https://testnet.monadexplorer.com';

export interface RequestArguments {
  method: string;
  params?: unknown[] | Record<string, unknown>;
}

export interface EthereumProvider {
  request: (args: RequestArguments) => Promise<unknown>;
  on?: (eventName: string, listener: (...args: any[]) => void) => void;
  removeListener?: (eventName: string, listener: (...args: any[]) => void) => void;
  isMetaMask?: boolean;
}

declare global {
  interface Window {
    ethereum?: EthereumProvider;
  }
}

/**
 * Detect injected EVM provider from window object.
 */
export function detectProvider(): EthereumProvider | null {
  if (typeof window === 'undefined') return null;
  return window.ethereum ?? null;
}

/**
 * Connect wallet by requesting accounts via EIP-1193 eth_requestAccounts.
 */
export async function connectWallet(): Promise<string> {
  const provider = detectProvider();
  if (!provider) {
    throw new Error(
      'No EVM wallet detected. Please install MetaMask, Rabby, or another compatible wallet.'
    );
  }

  try {
    const accounts = (await provider.request({
      method: 'eth_requestAccounts',
    })) as string[];

    if (!accounts || accounts.length === 0 || !accounts[0]) {
      throw new Error('No accounts returned by wallet.');
    }

    const address = accounts[0].trim();
    if (!/^0x[a-fA-F0-9]{40}$/.test(address)) {
      throw new Error('Wallet returned an invalid Ethereum address format.');
    }

    return address;
  } catch (err: any) {
    if (err?.code === 4001 || err?.message?.toLowerCase().includes('user rejected')) {
      throw new Error('Wallet connection was cancelled.');
    }
    throw new Error(err?.message || 'Failed to connect wallet.');
  }
}

/**
 * Get currently connected account (read-only without triggering popup).
 */
export async function getConnectedAddress(): Promise<string | null> {
  const provider = detectProvider();
  if (!provider) return null;

  try {
    const accounts = (await provider.request({
      method: 'eth_accounts',
    })) as string[];

    if (!accounts || accounts.length === 0 || !accounts[0]) {
      return null;
    }
    const address = accounts[0].trim();
    return /^0x[a-fA-F0-9]{40}$/.test(address) ? address : null;
  } catch {
    return null;
  }
}

/**
 * Get current connected Chain ID as integer.
 */
export async function getChainId(): Promise<number | null> {
  const provider = detectProvider();
  if (!provider) return null;

  try {
    const chainIdHex = (await provider.request({
      method: 'eth_chainId',
    })) as string | number;

    if (typeof chainIdHex === 'number') {
      return chainIdHex;
    }
    if (typeof chainIdHex === 'string') {
      return parseInt(chainIdHex, 16);
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Switch or add Monad Testnet (Chain ID 10143 / 0x279F).
 */
export async function switchToMonadTestnet(): Promise<boolean> {
  const provider = detectProvider();
  if (!provider) {
    throw new Error('No EVM wallet detected.');
  }

  try {
    await provider.request({
      method: 'wallet_switchEthereumChain',
      params: [{ chainId: MONAD_CHAIN_ID_HEX }],
    });
    return true;
  } catch (switchError: any) {
    // 4902 indicates that the chain has not been added to the wallet yet
    if (
      switchError?.code === 4902 ||
      switchError?.message?.toLowerCase().includes('unrecognized') ||
      switchError?.message?.toLowerCase().includes('not added')
    ) {
      try {
        await provider.request({
          method: 'wallet_addEthereumChain',
          params: [
            {
              chainId: MONAD_CHAIN_ID_HEX,
              chainName: MONAD_CHAIN_NAME,
              nativeCurrency: MONAD_NATIVE_CURRENCY,
              rpcUrls: [MONAD_RPC_URL],
              blockExplorerUrls: [MONAD_EXPLORER_URL],
            },
          ],
        });
        return true;
      } catch (addError: any) {
        if (addError?.code === 4001 || addError?.message?.toLowerCase().includes('user rejected')) {
          throw new Error('Network addition was cancelled.');
        }
        throw new Error(addError?.message || 'Failed to add Monad Testnet to wallet.');
      }
    }

    if (switchError?.code === 4001 || switchError?.message?.toLowerCase().includes('user rejected')) {
      throw new Error('Network switch was cancelled.');
    }
    throw new Error(switchError?.message || 'Failed to switch to Monad Testnet.');
  }
}

/**
 * Sign SIWE challenge string using personal_sign.
 */
export async function signMessage(message: string, address: string): Promise<string> {
  const provider = detectProvider();
  if (!provider) {
    throw new Error('No EVM wallet detected.');
  }

  try {
    // EIP-1193 personal_sign parameter convention: [message, address]
    const signature = (await provider.request({
      method: 'personal_sign',
      params: [message, address],
    })) as string;

    if (!signature || typeof signature !== 'string') {
      throw new Error('Invalid signature returned by wallet.');
    }

    return signature.startsWith('0x') ? signature : `0x${signature}`;
  } catch (err: any) {
    if (err?.code === 4001 || err?.message?.toLowerCase().includes('user rejected')) {
      throw new Error('Signature request was cancelled by the user.');
    }
    throw new Error(err?.message || 'Failed to sign message.');
  }
}

/**
 * Format address for UI badge (e.g. 0x71C2...43F0).
 */
export function formatAddress(address: string | null | undefined): string {
  if (!address) return '';
  const trimmed = address.trim();
  if (trimmed.length < 12) return trimmed;
  return `${trimmed.slice(0, 6)}...${trimmed.slice(-4)}`;
}

/**
 * Subscribe to accountsChanged event. Returns cleanup unsubscribe function.
 */
export function onAccountsChanged(callback: (accounts: string[]) => void): () => void {
  const provider = detectProvider();
  if (!provider?.on || !provider?.removeListener) return () => {};

  const handler = (accounts: string[]) => callback(accounts);
  provider.on('accountsChanged', handler);
  return () => {
    provider.removeListener?.('accountsChanged', handler);
  };
}

/**
 * Subscribe to chainChanged event. Returns cleanup unsubscribe function.
 */
export function onChainChanged(callback: (chainId: string) => void): () => void {
  const provider = detectProvider();
  if (!provider?.on || !provider?.removeListener) return () => {};

  const handler = (chainId: string) => callback(chainId);
  provider.on('chainChanged', handler);
  return () => {
    provider.removeListener?.('chainChanged', handler);
  };
}
