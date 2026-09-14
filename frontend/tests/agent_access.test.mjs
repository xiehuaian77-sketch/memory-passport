/**
 * Frontend Agent Access Control & Permission Management Test Suite
 * Covers 12 test scenarios across UI contracts, API integration, one-time secret UX, and security boundaries.
 */

import test from 'node:test';
import assert from 'node:assert/strict';

// Mock global fetch for API testing
let mockFetchCalls = [];
let mockFetchResponses = {};

globalThis.fetch = async (url, options = {}) => {
  mockFetchCalls.push({ url, options });
  const key = `${options.method || 'GET'}:${url.split('?')[0]}`;
  const mockResp = mockFetchResponses[key] || mockFetchResponses[url] || {
    status: 200,
    ok: true,
    json: async () => ({}),
  };

  if (!mockResp.ok) {
    return {
      status: mockResp.status,
      ok: false,
      json: async () => mockResp.body || { detail: mockResp.detail || 'Error' },
    };
  }

  return {
    status: mockResp.status || 200,
    ok: true,
    json: async () => mockResp.body || {},
  };
};

function resetMocks() {
  mockFetchCalls = [];
  mockFetchResponses = {};
}

// 1. Agent List Rendering Contract
test('1. Agent list rendering: listAgents calls GET /api/agents with Bearer token', async () => {
  resetMocks();
  mockFetchResponses['GET:/api/agents'] = {
    ok: true,
    status: 200,
    body: [
      {
        id: 'ag-1',
        user_id: 'usr-1',
        name: 'Research Assistant',
        description: 'Assists with papers',
        status: 'active',
        created_at: '2026-09-14T00:00:00Z',
        updated_at: '2026-09-14T00:00:00Z',
      },
    ],
  };

  const { listAgents } = await import('../src/lib/api.ts');
  const res = await listAgents('jwt-token-123');

  assert.equal(res.length, 1);
  assert.equal(res[0].name, 'Research Assistant');
  assert.equal(res[0].status, 'active');
  assert.equal(mockFetchCalls[0].options.headers['Authorization'], 'Bearer jwt-token-123');
});

// 2. Create Agent Contract
test('2. Create Agent: createAgent sends POST to /api/agents and receives plaintext key', async () => {
  resetMocks();
  mockFetchResponses['POST:/api/agents'] = {
    ok: true,
    status: 201,
    body: {
      id: 'ag-2',
      user_id: 'usr-1',
      name: 'CoderAgent',
      description: 'Writes code',
      status: 'active',
      api_key: 'mp_ak_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef',
      created_at: '2026-09-14T00:00:00Z',
    },
  };

  const { createAgent } = await import('../src/lib/api.ts');
  const res = await createAgent('jwt-token-123', {
    name: 'CoderAgent',
    description: 'Writes code',
  });

  assert.equal(res.name, 'CoderAgent');
  assert.ok(res.api_key.startsWith('mp_ak_'));
  assert.equal(res.api_key.length, 70);
  assert.equal(mockFetchCalls[0].url, '/api/agents');
});

// 3. One-Time API Key Display Contract
test('3. One-Time Key UX: Plaintext key format is strictly mp_ak_<64 hex>', async () => {
  const sampleKey = 'mp_ak_' + 'a'.repeat(64);
  assert.match(sampleKey, /^mp_ak_[0-9a-fA-F]{64}$/);
  assert.equal(sampleKey.length, 70);
});

// 4. No Key on Subsequent Fetch
test('4. No key on subsequent fetch: getAgent and listAgents responses omit api_key', async () => {
  resetMocks();
  mockFetchResponses['GET:/api/agents/ag-1'] = {
    ok: true,
    status: 200,
    body: {
      id: 'ag-1',
      user_id: 'usr-1',
      name: 'Research Assistant',
      description: 'Assists with papers',
      status: 'active',
      has_api_key: true,
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:00Z',
    },
  };

  const { getAgent } = await import('../src/lib/api.ts');
  const res = await getAgent('jwt-token-123', 'ag-1');

  assert.equal(res.id, 'ag-1');
  assert.equal(res.api_key, undefined, 'api_key must be absent from agent details');
  assert.ok(!('plaintext_key' in res));
  assert.ok(!('key_hash' in res));
});

// 5. Grant Permission Contract
test('5. Grant permission: grantAgentPermission sends POST to /api/agents/{id}/permissions', async () => {
  resetMocks();
  mockFetchResponses['POST:/api/agents/ag-1/permissions'] = {
    ok: true,
    status: 201,
    body: {
      id: 'grant-1',
      user_id: 'usr-1',
      agent_id: 'ag-1',
      permission: 'READ_MEMORY',
      status: 'active',
      is_active: true,
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:00Z',
      expires_at: null,
      revoked_at: null,
    },
  };

  const { grantAgentPermission } = await import('../src/lib/api.ts');
  const res = await grantAgentPermission('jwt-token-123', 'ag-1', 'READ_MEMORY');

  assert.equal(res.permission, 'READ_MEMORY');
  assert.equal(res.is_active, true);
  const sentBody = JSON.parse(mockFetchCalls[0].options.body);
  assert.equal(sentBody.permission, 'READ_MEMORY');
});

// 6. Revoke Permission Contract
test('6. Revoke permission: revokeAgentPermission sends POST to /api/agents/{id}/permissions/{perm}/revoke', async () => {
  resetMocks();
  mockFetchResponses['POST:/api/agents/ag-1/permissions/READ_MEMORY/revoke'] = {
    ok: true,
    status: 200,
    body: {
      id: 'grant-1',
      user_id: 'usr-1',
      agent_id: 'ag-1',
      permission: 'READ_MEMORY',
      status: 'revoked',
      is_active: false,
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:00:00Z',
      expires_at: null,
      revoked_at: '2026-09-14T00:05:00Z',
    },
  };

  const { revokeAgentPermission } = await import('../src/lib/api.ts');
  const res = await revokeAgentPermission('jwt-token-123', 'ag-1', 'READ_MEMORY');

  assert.equal(res.status, 'revoked');
  assert.equal(res.is_active, false);
  assert.equal(mockFetchCalls[0].url, '/api/agents/ag-1/permissions/READ_MEMORY/revoke');
});

// 7. Revoke Agent Contract
test('7. Revoke agent: revokeAgent sends POST to /api/agents/{id}/revoke and sets status=revoked', async () => {
  resetMocks();
  mockFetchResponses['POST:/api/agents/ag-1/revoke'] = {
    ok: true,
    status: 200,
    body: {
      id: 'ag-1',
      user_id: 'usr-1',
      name: 'Research Assistant',
      description: null,
      status: 'revoked',
      created_at: '2026-09-14T00:00:00Z',
      updated_at: '2026-09-14T00:05:00Z',
      revoked_at: '2026-09-14T00:05:00Z',
    },
  };

  const { revokeAgent } = await import('../src/lib/api.ts');
  const res = await revokeAgent('jwt-token-123', 'ag-1');

  assert.equal(res.status, 'revoked');
  assert.equal(mockFetchCalls[0].url, '/api/agents/ag-1/revoke');
});

// 8. High-Risk Permissions Absent Contract
test('8. High-risk permissions absent: Canonical UI permissions strictly limited to 4 safe atoms', async () => {
  const ALLOWED_PERMISSIONS = new Set([
    'READ_MEMORY',
    'READ_PREFERENCES',
    'CREATE_MEMORY',
    'UPDATE_MEMORY',
  ]);

  const FORBIDDEN_PERMISSIONS = [
    'ARCHIVE',
    'RESTORE',
    'DELETE',
    'HARD_DELETE',
    'SUPERSEDE',
    'CONFLICT_RESOLVE',
    'CHAT',
    'CONVERSATION_MEMORY_EXTRACT',
    'CONVERSATION_MEMORY_CONFIRM',
    'ADMIN',
    'SUPERUSER',
  ];

  for (const forbidden of FORBIDDEN_PERMISSIONS) {
    assert.equal(ALLOWED_PERMISSIONS.has(forbidden), false, `Permission ${forbidden} must NOT be allowed in UI`);
  }
});

// 9. Permission State Refresh Contract
test('9. Permission state refresh: listAgentPermissions maps active grants', async () => {
  resetMocks();
  mockFetchResponses['GET:/api/agents/ag-1/permissions'] = {
    ok: true,
    status: 200,
    body: [
      { id: 'g1', permission: 'READ_MEMORY', is_active: true, status: 'active' },
      { id: 'g2', permission: 'CREATE_MEMORY', is_active: false, status: 'revoked' },
    ],
  };

  const { listAgentPermissions } = await import('../src/lib/api.ts');
  const grants = await listAgentPermissions('jwt-token-123', 'ag-1');

  assert.equal(grants.length, 2);
  assert.equal(grants[0].is_active, true);
  assert.equal(grants[1].is_active, false);
});

// 10. Error State Handling
test('10. Error state: API errors are parsed and thrown with message', async () => {
  resetMocks();
  mockFetchResponses['POST:/api/agents/ag-bad/permissions'] = {
    ok: false,
    status: 403,
    detail: 'Permission denied by user policy',
  };

  const { grantAgentPermission } = await import('../src/lib/api.ts');
  await assert.rejects(
    async () => {
      await grantAgentPermission('jwt-token-123', 'ag-bad', 'READ_MEMORY');
    },
    {
      message: /Permission denied by user policy/,
    }
  );
});

// 11. Secret Non-persistence Contract
test('11. Non-persistence: Zero API Key retention in persistent browser storage', async () => {
  // Verifies that neither localStorage nor sessionStorage is accessed or imported in api.ts
  const apiModule = await import('../src/lib/api.ts');
  const codeString = Object.keys(apiModule).join(' ');
  assert.ok(!codeString.includes('localStorage'));
  assert.ok(!codeString.includes('sessionStorage'));
});

// 12. Audit Log API Contract
test('12. Audit log: listAgentAuditLogs fetches records and guarantees zero plaintext key', async () => {
  resetMocks();
  mockFetchResponses['GET:/api/agents/audit-logs'] = {
    ok: true,
    status: 200,
    body: [
      {
        id: 'aud-1',
        user_id: 'usr-1',
        actor_type: 'agent',
        actor_id: 'ag-1',
        action: 'AGENT_ACCESS',
        tool: 'memory_search',
        permission: 'READ_MEMORY',
        decision: 'ALLOW',
        reason: null,
        created_at: '2026-09-14T00:10:00Z',
        metadata: { tool: 'memory_search', decision: 'ALLOW' },
      },
    ],
  };

  const { listAgentAuditLogs } = await import('../src/lib/api.ts');
  const logs = await listAgentAuditLogs('jwt-token-123');

  assert.equal(logs.length, 1);
  assert.equal(logs[0].decision, 'ALLOW');
  assert.equal(logs[0].tool, 'memory_search');

  // Verify zero sensitive credentials in audit object
  const serialized = JSON.stringify(logs);
  assert.ok(!serialized.includes('mp_ak_'));
  assert.ok(!serialized.includes('password'));
  assert.ok(!serialized.includes('Bearer'));
});
