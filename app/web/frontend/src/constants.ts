/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export const COLORS = {
  CHARCOAL: '#434343',
  GOLD: '#F7C873',
  PARCHMENT: '#FAEBCD',
  CLOUD: '#F8F8F8',
};

export const MOCK_DATA = {
  employees: [
    { id: "sarah_chen_mktg", name: "Sarah Chen", department: "Marketing", role: "Social Media Manager", manager_id: "james_torres_mktg" },
    { id: "raj_kumar_bd", name: "Raj Kumar", department: "Business Development", role: "BD Manager", manager_id: "sandra_lee_bd" }
  ],
  claims: [
    {
      claim_id: "CLM-2024-047",
      employee_id: "sarah_chen_mktg",
      raw_text: "Hey, I need to get reimbursed for the Canva Pro subscription I bought for the social media campaign. It's $12.99/month, I've been paying for 3 months. Also that Uber ride to the client meeting last week, I think it was around $35? And I bought a wireless mouse from Amazon for $29.99 because my old one broke.",
      items: [
        { item_id: "A", category: "subscription", vendor: "Canva Pro", amount: 38.97, decision: "manager_acknowledge", reason: "Team license available. Awaiting justification.", confidence: 0.71 },
        { item_id: "B", category: "travel", vendor: "Uber", amount: 35.00, decision: "auto_approve", reason: "Travel context validated, within policy limits.", confidence: 0.92 },
        { item_id: "C", category: "equipment", vendor: "Amazon", amount: 29.99, decision: "conditional_approve", reason: "Receipt required for purchase over $25.", confidence: 0.73 }
      ]
    },
    {
      claim_id: "CLM-2024-048",
      employee_id: "raj_kumar_bd",
      raw_text: "Need reimbursement for Zoom Pro I've been paying myself, $13.33/month for 6 months. Also Grab ride to client meeting $22.",
      items: [
        { item_id: "A", category: "subscription", vendor: "Zoom Pro", amount: 79.98, decision: "reject", reason: "Zoom Business already provisioned to your account.", confidence: 0.97 },
        { item_id: "B", category: "travel", vendor: "Grab", amount: 22.00, decision: "auto_approve", reason: "Valid client meeting travel.", confidence: 0.95 }
      ]
    }
  ],
  policies: [
    { rule_id: "SUB-001", title: "Individual SaaS Subscription", text: "Only reimbursable if no team license available." },
    { rule_id: "TRV-001", title: "Local Travel", text: "Reimbursable up to $50 per trip via approved ride services." },
    { rule_id: "EQP-001", title: "Equipment Replacement", text: "Under $75 reimbursable with manager acknowledgment. Receipt required over $25." }
  ]
};
