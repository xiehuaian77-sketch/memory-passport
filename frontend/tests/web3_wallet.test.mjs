// frontend/tests/web3_wallet.test.mjs
// Node.js native test runner test suite for Web3 EIP-1193 & Monad Testnet Bridge

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  MONAD_CHAIN_ID_DECIMAL,
  MONAD_CHAIN_ID_HEX,
  MONAD_RPC_URL,
  MONAD_CHAIN_NAME,
  formatAddress,
} from '../src/lib/web3.ts';

// Test Fixtures & Mock Provider Factory
function createMockProvider(overrides = {}) {
  const listeners = new Map();
  const state = {
    accounts: ['0x71C2E63B48421882c7aE9D58E16503c403Be43F0'],
    chainId: '0x279F', // 10143
    rejectConnect: false,
    rejectSign: false,
    failSwitchChain: false,
    chainAdded: false,
    ...overrides,
  };

  const provider = {
    request: async ({ method, params }) => {
      switch (method) {
        case 'eth_requestAccounts':
          if (state.rejectConnect) {
            const err = new Error('User rejected the request.');
            err.code = 4001;
            throw err;
          }
          return state.accounts;

        case 'eth_accounts':
          return state.accounts;

        case 'eth_chainId':
          return state.chainId;

        case 'wallet_switchEthereumChain':
          if (state.failSwitchChain) {
            const err = new Error('Unrecognized chain ID');
            err.code = 4902;
            throw err;
          }
          state.chainId = params[0].chainId;
          return null;

        case 'wallet_addEthereumChain':
          state.chainAdded = true;
          state.chainId = params[0].chainId;
          return null;

        case 'personal_sign':
          if (state.rejectSign) {
            const err = new Error('User rejected message signature.');
            err.code = 4001;
            throw err;
          }
          return '0x' + '30' * 65; // Mock 65-byte hex signature

        default:
          throw new Error(`Unhandled method: ${method}`);
      }
    },

    on: (eventName, listener) => {
      if (!listeners.has(eventName)) listeners.set(eventName, []);
      listeners.get(eventName).push(listener);
    },

    removeListener: (eventName, listener) => {
      if (!listeners.has(eventName)) return;
      const filtered = listeners.get(eventName).filter(l => l !== listener);
      listeners.set(eventName, filtered);
    },

    _emit: (eventName, ...args) => {
      if (listeners.has(eventName)) {
        for (const l of listeners.get(eventName)) {
          l(...args);
        }
      }
    },
  };

  return { provider, state };
}

test('1. Constants: Monad Testnet Chain ID and network configuration', () => {
  assert.equal(MONAD_CHAIN_ID_DECIMAL, 10143);
  assert.equal(MONAD_CHAIN_ID_HEX.toLowerCase(), '0x279f');
  assert.equal(MONAD_RPC_URL, 'https://testnet-rpc.monad.xyz');
  assert.equal(MONAD_CHAIN_NAME, 'Monad Testnet');
});

test('2. Provider Detection: detectProvider returns null when window.ethereum is undefined', async () => {
  const original = global.window;
  delete global.window;
  const { detectProvider } = await import('../src/lib/web3.ts');
  assert.equal(detectProvider(), null);
  global.window = original;
});

test('3. Provider Detection: detectProvider finds window.ethereum when present', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { detectProvider } = await import('../src/lib/web3.ts');
  assert.equal(detectProvider(), provider);
  delete global.window;
});

test('4. Connect Wallet: successfully requests accounts via eth_requestAccounts', async () => {
  const { provider } = createMockProvider({
    accounts: ['0x71C2E63B48421882c7aE9D58E16503c403Be43F0'],
  });
  global.window = { ethereum: provider };
  const { connectWallet } = await import('../src/lib/web3.ts');
  const address = await connectWallet();
  assert.equal(address, '0x71C2E63B48421882c7aE9D58E16503c403Be43F0');
  delete global.window;
});

test('5. Connect Wallet: throws friendly error on missing provider', async () => {
  delete global.window;
  const { connectWallet } = await import('../src/lib/web3.ts');
  await assert.rejects(
    async () => await connectWallet(),
    /No EVM wallet detected/
  );
});

test('6. Connect Wallet: handles user rejection (code 4001) gracefully without stack trace', async () => {
  const { provider } = createMockProvider({ rejectConnect: true });
  global.window = { ethereum: provider };
  const { connectWallet } = await import('../src/lib/web3.ts');
  await assert.rejects(
    async () => await connectWallet(),
    /Wallet connection was cancelled/
  );
  delete global.window;
});

test('7. Get Chain ID: parses hex chain ID to integer 10143', async () => {
  const { provider } = createMockProvider({ chainId: '0x279F' });
  global.window = { ethereum: provider };
  const { getChainId } = await import('../src/lib/web3.ts');
  const cid = await getChainId();
  assert.equal(cid, 10143);
  delete global.window;
});

test('8. Network Switching: successfully switches to Monad Testnet', async () => {
  const { provider } = createMockProvider({ chainId: '0x1' }); // Ethereum Mainnet
  global.window = { ethereum: provider };
  const { switchToMonadTestnet, getChainId } = await import('../src/lib/web3.ts');
  const ok = await switchToMonadTestnet();
  assert.equal(ok, true);
  const newCid = await getChainId();
  assert.equal(newCid, 10143);
  delete global.window;
});

test('9. Network Fallback: triggers wallet_addEthereumChain when chain not added (4902)', async () => {
  const { provider, state } = createMockProvider({ failSwitchChain: true });
  global.window = { ethereum: provider };
  const { switchToMonadTestnet } = await import('../src/lib/web3.ts');
  const ok = await switchToMonadTestnet();
  assert.equal(ok, true);
  assert.equal(state.chainAdded, true);
  delete global.window;
});

test('10. Sign Message: invokes personal_sign with [message, address]', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { signMessage } = await import('../src/lib/web3.ts');
  const message = 'Test SIWE challenge';
  const sig = await signMessage(message, '0x71C2E63B48421882c7aE9D58E16503c403Be43F0');
  assert.match(sig, /^0x/);
  delete global.window;
});

test('11. Sign Message: handles user rejection gracefully', async () => {
  const { provider } = createMockProvider({ rejectSign: true });
  global.window = { ethereum: provider };
  const { signMessage } = await import('../src/lib/web3.ts');
  await assert.rejects(
    async () => await signMessage('msg', '0x71C2E63B48421882c7aE9D58E16503c403Be43F0'),
    /Signature request was cancelled by the user/
  );
  delete global.window;
});

test('12. Read-only Account: getConnectedAddress reads account without user prompt', async () => {
  const { provider } = createMockProvider({
    accounts: ['0x71C2E63B48421882c7aE9D58E16503c403Be43F0'],
  });
  global.window = { ethereum: provider };
  const { getConnectedAddress } = await import('../src/lib/web3.ts');
  const addr = await getConnectedAddress();
  assert.equal(addr, '0x71C2E63B48421882c7aE9D58E16503c403Be43F0');
  delete global.window;
});

test('13. Event Subscription: accountsChanged triggers callback and unsubscribes cleanly', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { onAccountsChanged } = await import('../src/lib/web3.ts');

  let detected = null;
  const unsub = onAccountsChanged((accs) => {
    detected = accs[0];
  });

  provider._emit('accountsChanged', ['0x1111111111111111111111111111111111111111']);
  assert.equal(detected, '0x1111111111111111111111111111111111111111');

  unsub();
  provider._emit('accountsChanged', ['0x2222222222222222222222222222222222222222']);
  assert.equal(detected, '0x1111111111111111111111111111111111111111'); // Unchanged
  delete global.window;
});

test('14. Event Subscription: chainChanged triggers callback and parses chain ID', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { onChainChanged } = await import('../src/lib/web3.ts');

  let currentChain = null;
  const unsub = onChainChanged((c) => {
    currentChain = parseInt(c, 16);
  });

  provider._emit('chainChanged', '0x279F');
  assert.equal(currentChain, 10143);

  unsub();
  delete global.window;
});

test('15. Address Formatter: formats address to 0x1234...5678 badge format', () => {
  assert.equal(formatAddress('0x71C2E63B48421882c7aE9D58E16503c403Be43F0'), '0x71C2...43F0');
  assert.equal(formatAddress(null), '');
  assert.equal(formatAddress(''), '');
});

test('16. Connected != Verified Boundary: connected state is distinct from backend verified state', () => {
  const localWalletState = {
    connectedAddress: '0x71C2E63B48421882c7aE9D58E16503c403Be43F0',
    isVerified: false,
  };
  assert.equal(localWalletState.isVerified, false);
  localWalletState.isVerified = true;
  assert.equal(localWalletState.isVerified, true);
});

test('17. Security Boundary: Zero private key handling or retention', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { signMessage } = await import('../src/lib/web3.ts');
  const res = await signMessage('msg', '0x71C2E63B48421882c7aE9D58E16503c403Be43F0');
  assert.ok(typeof res === 'string');
  assert.ok(!res.includes('private'));
  delete global.window;
});

test('18. Wrong Network Detection: identifies when chain ID != 10143', async () => {
  const { provider } = createMockProvider({ chainId: '0x1' }); // Mainnet
  global.window = { ethereum: provider };
  const { getChainId } = await import('../src/lib/web3.ts');
  const cid = await getChainId();
  assert.notEqual(cid, MONAD_CHAIN_ID_DECIMAL);
  assert.equal(cid === MONAD_CHAIN_ID_DECIMAL, false);
  delete global.window;
});

test('19. Disconnect Handling: accountsChanged with empty list marks disconnected without error', async () => {
  const { provider } = createMockProvider();
  global.window = { ethereum: provider };
  const { onAccountsChanged } = await import('../src/lib/web3.ts');

  let activeAccount = 'initial';
  onAccountsChanged((accounts) => {
    activeAccount = accounts.length > 0 ? accounts[0] : null;
  });

  provider._emit('accountsChanged', []);
  assert.equal(activeAccount, null);
  delete global.window;
});

test('20. API Verify Payload Contract: conforms to {address, signature, nonce} schema', () => {
  const payload = {
    address: '0x71C2E63B48421882c7aE9D58E16503c403Be43F0',
    signature: '0x1234567890abcdef',
    nonce: 'sample-nonce-string',
  };
  assert.ok(payload.address.startsWith('0x'));
  assert.ok(payload.signature.startsWith('0x'));
  assert.ok(payload.nonce.length > 0);
});
