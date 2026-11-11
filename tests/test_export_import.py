import json
import pytest
from imperal_sdk.testing import MockContext
from main import (
    create_brand_profile,
    add_brand_competitor,
    create_target_segment,
    run_swot_analysis,
    export_brand_project,
    import_brand_project,
    _render_brand_detail_panel,
)
from schemas import (
    CreateBrandProfileParams,
    AddCompetitorParams,
    CreateTargetSegmentParams,
    RunSWOTAnalysisParams,
    ExportBrandProjectParams,
    ImportBrandProjectParams,
)

@pytest.mark.asyncio
async def test_export_import_full():
    ctx1 = MockContext(user_id="u1", tenant_id="t1")
    ctx2 = MockContext(user_id="u2", tenant_id="t2")

    p = await create_brand_profile(
        ctx1,
        CreateBrandProfileParams(
            brand_name="RocketCorp",
            mission="Launch reliably",
            vision="Orbit",
            value_proposition="Low cost",
            tone_of_voice="Direct",
            unique_selling_points=["Reusability"],
            content_topics=["Aerospace"],
        ),
    )
    b_id = p.data.id

    await add_brand_competitor(
        ctx1,
        AddCompetitorParams(
            brand_id=b_id,
            name="OldSpace Inc",
            notes="Slow and costly",
        ),
    )

    await create_target_segment(
        ctx1,
        CreateTargetSegmentParams(
            brand_id=b_id,
            segment_name="Sat Builders",
        ),
    )

    await run_swot_analysis(
        ctx1,
        RunSWOTAnalysisParams(
            brand_id=b_id,
        ),
    )

    # Export
    exp = await export_brand_project(ctx1, ExportBrandProjectParams(brand_id=b_id))
    assert exp.status == "success"
    raw_json = exp.data.json_data
    assert raw_json

    data = json.loads(raw_json)
    assert data["brand_id"] == b_id
    assert data["brand_profile"]["data"]["brand_name"] == "RocketCorp"
    assert len(data["collections"]["competitor_profiles"]) == 1
    assert len(data["collections"]["target_segments"]) == 1
    assert len(data["collections"]["swot_results"]) == 1

    # Import into ctx2 (cross-account)
    imp = await import_brand_project(ctx2, ImportBrandProjectParams(json_data=raw_json))
    assert imp.status == "success"
    assert imp.data.brand_id == b_id

    # Verify ctx2 has data
    b2 = await ctx2.store.get("brand_profiles", b_id)
    assert b2 is not None
    assert b2.data["brand_name"] == "RocketCorp"
    assert b2.data["mission"] == "Launch reliably"

    comps = await ctx2.store.query("competitor_profiles", where={"brand_id": b_id})
    assert len(comps.data) == 1
    assert comps.data[0].data["name"] == "OldSpace Inc"

    segs = await ctx2.store.query("target_segments", where={"brand_id": b_id})
    assert len(segs.data) == 1
    assert segs.data[0].data["segment_name"] == "Sat Builders"

    swots = await ctx2.store.query("swot_results", where={"brand_id": b_id})
    assert len(swots.data) == 1
    assert "Reusability" in swots.data[0].data["strengths"]

@pytest.mark.asyncio
async def test_import_with_storeclient_set_signature():
    """Regression test for 'StoreClient.set() takes 3 positional arguments but 4 were given'.
    
    Real StoreClient.set signature is:
        async def set(self, key: str, data: Any) -> Document
    where key is 'collection/doc_id'.
    """
    ctx = MockContext(user_id="u3", tenant_id="t3")
    set_calls = []

    async def mock_set(key: str, data):
        set_calls.append((key, data))
        collection, doc_id = key.split("/", 1)
        # Delegate to standard mock store create or update
        try:
            return await ctx.store.update(collection, doc_id, data)
        except Exception:
            return await ctx.store.create(collection, data)

    # Attach set method matching StoreClient.set signature
    ctx.store.set = mock_set

    test_bundle = {
        "version": "1.0",
        "brand_id": "test-b-1",
        "brand_profile": {
            "id": "test-b-1",
            "data": {
                "id": "test-b-1",
                "brand_name": "SetSignatureTest",
                "mission": "Test StoreClient.set call",
            }
        },
        "collections": {}
    }
    raw_json = json.dumps(test_bundle)
    res = await import_brand_project(ctx, ImportBrandProjectParams(json_data=raw_json))
    assert res.status == "success"
    assert len(set_calls) > 0
    assert set_calls[0][0] == "brand_profiles/test-b-1"
    assert set_calls[0][1]["brand_name"] == "SetSignatureTest"


@pytest.mark.asyncio
async def test_panel_has_export_and_import():
    ctx = MockContext(user_id="u1", tenant_id="t1")
    p = await create_brand_profile(
        ctx,
        CreateBrandProfileParams(
            brand_name="PanelTest",
            mission="Testing panel UI",
        ),
    )
    b_id = p.data.id

    panel = await _render_brand_detail_panel(ctx, brand_id=b_id, tab="profile")
    serialized = str(panel)
    assert "export_brand_project" in serialized
    assert "import_brand_project" in serialized
    assert "Export Project (JSON)" in serialized
    assert "Import Project (JSON)" in serialized

    # Test export modal rendering (regression test for TypeError: unexpected keyword argument 'on_cancel')
    panel_export = await _render_brand_detail_panel(ctx, brand_id=b_id, tab="profile", show_export="1")
    serialized_export = str(panel_export)
    assert "Export Project · PanelTest" in serialized_export
    assert "Download paneltest-brand-project-export.json" in serialized_export

    # Test import modal rendering
    panel_import = await _render_brand_detail_panel(ctx, brand_id=b_id, tab="profile", show_import="1")
    serialized_import = str(panel_import)
    assert "Import Project · PanelTest" in serialized_import
    assert "Paste project JSON here..." in serialized_import
    assert "import_brand_project" in serialized_import
    assert "Import Project" in serialized_import

    # Test erase button and confirmation modal rendering
    assert "Erase all project data" in serialized
    panel_erase = await _render_brand_detail_panel(ctx, brand_id=b_id, tab="profile", show_erase="1")
    serialized_erase = str(panel_erase)
    assert "Erase All Project Data · PanelTest" in serialized_erase
    assert "action is irreversible" in serialized_erase
    assert "delete_brand_profile" in serialized_erase
    assert "Erase Everything (Irreversible)" in serialized_erase

def test_backups_exist():
    import os
    assert os.path.exists("backups/main.py.bak")
    assert os.path.exists("backups/schemas.py.bak")



@pytest.mark.asyncio
async def test_import_user_payload():
    """Reproduce import with user's exact JSON export payload."""
    user_payload = {
        "format": "imperal:brand_project_export:v1",
        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
        "brand_profile": {
            "id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
            "data": {
                "site_id": "ksrenovationgroup.com",
                "brand_name": "KS Renovation Group",
                "mission": "Deliver uncompromising architectural craftsmanship, white-glove project management, and complete peace of mind for luxury residential renovations across Manhattan and Brooklyn.",
                "vision": "To be the premier bespoke general contracting partner for NYC's top interior designers, architects, and discerning luxury homeowners.",
                "value_proposition": "White-glove full-gut renovation management with direct principal oversight, meticulous craftsmanship, and frictionless NYC building board navigation.",
                "tone_of_voice": "Authoritative, discreet, sophisticated, calm, and technically precise",
                "unique_selling_points": [
                    "Deep mastery of strict NYC Co-op/Condo board alteration agreements, DOB permits & LPC preservation compliance",
                    "Dedicated site superintendent and direct principal oversight ensuring frictionless, on-time delivery",
                    "In-house architectural millwork, bespoke cabinetry, and fine European-standard finish execution",
                    "White-glove protection of building common areas, dust containment, and neighbor relations",
                    "Trusted execution partner for Manhattan's top interior designers and architectural practices"
                ],
                "industry": "Luxury Residential Renovation & General Contracting (NYC)",
                "content_topics": [
                    "High-End Full Gut Renovations",
                    "NYC Co-op & Condo Alteration Agreements & Approvals",
                    "Historic Brownstone Restoration & Structural Renovations",
                    "Luxury Kitchen & Primary Bathroom Remodeling",
                    "Architectural Millwork & Custom Cabinetry",
                    "Design-Build Collaboration with NYC Interior Designers",
                    "DOB Permitting & Landmarks Preservation Commission (LPC) Guidelines"
                ]
            }
        },
        "collections": {
            "competitor_profiles": [
                {
                    "id": "c08bfffe-7b5c-4812-b8f0-c5ea133acfe3",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "name": "Bolster (bolster.us)",
                        "url": "https://bolster.us",
                        "strengths": [
                            "Сильное позиционирование вокруг фиксированной цены и финансовой предсказуемости (Zero Financial Risk)",
                            "Мощная цифровая воронка и маркетинг в поисковой выдаче по высокочастотным запросам NYC renovation",
                            "Упакованные кейсы реконструкции таунхаусов и апартаментов"
                        ],
                        "weaknesses": [
                            "Корпоративный конвейерный подход без акцента на эксклюзивную авторскую столярку (bespoke architectural millwork)",
                            "Меньше гибкости при работе с кастомными материалами и чертежами топовых независимых дизайнеров",
                            "Фокус на стандартизированные процессы снижает привлекательность для ультра-элитных частных заказчиков"
                        ],
                        "notes": "Major NYC design-build competitor targeting high-budget residential renovations with a focus on cost transparency and fixed-price guarantees."
                    }
                },
                {
                    "id": "73038f8c-2347-456d-b330-9c6ab5ec15ab",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "name": "Gallery KBNY (Gallery Design Build)",
                        "url": "https://gallerykbny.com",
                        "strengths": [
                            "Strong brand recognition and aggressive digital marketing across Manhattan and Brooklyn",
                            "Full design-build turnkey messaging emphasizing single-point accountability",
                            "Extensive photographic portfolio of completed pre-war and modern apartment renovations"
                        ],
                        "weaknesses": [
                            "Can feel corporate and volume-driven compared to bespoke artisanal high-touch oversight",
                            "Higher overhead costs frequently passed onto clients in change orders",
                            "Less tailored white-glove communication for elite architectural interior designer partnerships"
                        ],
                        "notes": "Prominent NYC full-service design-build contractor specializing in Manhattan and Brooklyn co-op & condo gut renovations. Heavy digital marketing presence and portfolio showcase."
                    }
                }
            ],
            "target_segments": [
                {
                    "id": "44812e19-1ea2-4cca-8fe4-eaf0773cb778",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "segment_name": "NYC Elite Interior Designers & Architects",
                        "demographics": "Top AD100 and boutique NYC residential interior designers, licensed architects, and design studio principals managing luxury renovations in Manhattan and Brooklyn.",
                        "psychographics": "Reputation-first aesthetic perfectionists. They prize craftsmanship, discretion, calm competence, and a general contractor who acts as an invisible, reliable engineering arm of their creative vision.",
                        "pain_points": [
                            "Contractors making unauthorized design substitutions or compromising aesthetic intent without consulting the designer",
                            "Subcontractors damaging finished bespoke materials or missing critical installation tolerances",
                            "Combative or defensive communication creating friction with high-profile clients",
                            "Unreliable timelines delaying custom furniture deliveries and final photography styling"
                        ],
                        "needs": [
                            "Flawless execution of custom architectural details, bespoke millwork, and premium finishes strictly to drawing specifications",
                            "Zero contractor ego: proactive communication, consultative problem-solving, and complete respect for the designer-client relationship",
                            "Mastery of complex NYC Co-op/Condo alteration agreements, DOB filings, and strict building superintendents",
                            "Transparent estimating, reliable project scheduling, and pristine job-site cleanliness during all phases"
                        ],
                        "preferred_channels": [
                            "Direct architect/designer trade referrals",
                            "Architectural and interior design portfolio features (Architectural Digest, Elle Decor, Brownstoner)",
                            "Exclusive trade showrooms, design industry networking, and Instagram curation"
                        ]
                    }
                },
                {
                    "id": "5537218f-6d45-453c-8cb5-ac7499f6d3bb",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "segment_name": "Manhattan & Brooklyn Luxury Co-op / Condo / Brownstone Owners",
                        "demographics": "Ultra-High-Net-Worth (UHNW) homeowners, executives, and families living in Manhattan (Tribeca, UES, UWS, SoHo, West Village) and Brownstone Brooklyn (Brooklyn Heights, Cobble Hill, Park Slope). Home values $3M-$20M+.",
                        "psychographics": "Demanding, time-poor, discerning professionals. Value peace of mind, discretion, flawless aesthetics, and a calm, authoritative contractor who protects their time and investment.",
                        "pain_points": [
                            "Nightmare alter-agreement delays and board rejections costing months of rent",
                            "Contractors disappearing, sudden change-order inflation, and broken promises",
                            "Messy job sites, noise complaints from neighbors, and building superintendent fines",
                            "Substandard finish quality not matching multi-million dollar expectations"
                        ],
                        "needs": [
                            "Complete turnkey management: from DOB/LPC filings and Co-op board approval to white-glove handover",
                            "Absolute schedule and budget predictability with transparent milestone accounting",
                            "Flawless acoustic insulation, luxury bespoke finishes, and premium MEP integration",
                            "Discreet, courteous crew respecting luxury building regulations and neighbors"
                        ],
                        "preferred_channels": [
                            "Referrals from luxury interior designers, architects, and luxury real estate brokers (Corcoran, Compass, Sotheby's)",
                            "High-intent Google search for luxury co-op/condo gut renovation specialists in NYC",
                            "Architectural Digest, Dwell, Houzz editorial features and Instagram portfolio showcases"
                        ]
                    }
                },
                {
                    "id": "abd7b5c4-1425-4885-a0a2-479511ff1b64",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "segment_name": "NYC Luxury Interior Designers & Architectural Studios",
                        "demographics": "Manhattan & Brooklyn architectural firms, AD100 and boutique luxury interior design studios managing $2M-$15M+ residential transformations.",
                        "psychographics": "Aesthetic perfectionists and brand custodians. Value architectural integrity, trust, seamless craftsmanship, and contractors who make them look brilliant in front of their clients.",
                        "pain_points": [
                            "Contractors who alter architectural specs without permission or push cheap compromises",
                            "Unreliable schedules delaying custom furniture installations and editorial photoshoots",
                            "Damaged specialty finishes, imported stone, or custom fixtures on site",
                            "Poor site communication reflecting poorly on the designer's reputation"
                        ],
                        "needs": [
                            "100% fidelity to architectural drawings, material specifications, and design intent",
                            "Proactive shop drawings, trade coordination, and pre-construction clash resolution",
                            "Discreet, respectful representation in front of elite clients with zero contractor ego",
                            "Pristine millwork execution, seamless shadow reveals, and museum-grade finishes"
                        ],
                        "preferred_channels": [
                            "Direct trade partnerships and studio lunch-and-learns",
                            "Design industry networks, ASID NY Metro, and AIA New York",
                            "Collaborative project showcases on Instagram and design press features"
                        ]
                    }
                },
                {
                    "id": "8323858a-c7a3-42a4-8019-c09a59236c70",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "segment_name": "Manhattan Luxury Co-op & Condo Homeowners",
                        "demographics": "Age 35-65, HNW/UHNW executives, partners in finance/tech/law, Manhattan (UES, UWS, Tribeca, SoHo, West Village). Property value $2M-$15M+.",
                        "psychographics": "Time-poor, highly accomplished, value peace of mind, discretion, and control. Want to feel confidence, authority, and care without construction stress.",
                        "pain_points": [
                            "Fear of budget overruns, endless delays, and unaccountable general contractors",
                            "Intimidating building board bureaucracy, alteration agreements, and risk of stop-work orders",
                            "Disruption to demanding professional life and neighbor conflict in high-profile buildings",
                            "Compromised quality in hidden construction details and finish execution"
                        ],
                        "needs": [
                            "Frictionless Co-op/Condo board alteration approval and package compliance",
                            "White-glove protection of building common areas and strict noise/dust mitigation",
                            "Masterful architectural millwork, bespoke finishes, and premium European standards",
                            "Calm, proactive communication with dedicated site superintendent and schedule fidelity"
                        ],
                        "preferred_channels": [
                            "Architect and Interior Designer referrals",
                            "High-intent organic search (NYC Co-op renovation, pre-war gut renovation)",
                            "Word of mouth and building resident networks",
                            "Architectural Digest / luxury home features"
                        ]
                    }
                }
            ],
            "swot_results": [
                {
                    "id": "e12d8b62-fb09-48dd-8965-313b8c8c2fdc",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "strengths": [
                            "Deep mastery of strict NYC Co-op/Condo board alteration agreements, DOB permits & LPC preservation compliance",
                            "Dedicated site superintendent and direct principal oversight ensuring frictionless, on-time delivery",
                            "In-house architectural millwork, bespoke cabinetry, and fine European-standard finish execution",
                            "White-glove protection of building common areas, dust containment, and neighbor relations",
                            "Trusted execution partner for Manhattan's top interior designers and architectural practices",
                            "Clear value proposition: White-glove full-gut renovation management with direct principal oversight, meticulous craftsmanship, and frictionless NYC building board navigation.",
                            "Defined tone of voice: Authoritative, discreet, sophisticated, calm, and technically precise"
                        ],
                        "weaknesses": [
                            "Relative to Bolster (bolster.us), unmatched: Сильное позиционирование вокруг фиксированной цены и финансовой предсказуемости (Zero Financial Risk)",
                            "Relative to Bolster (bolster.us), unmatched: Упакованные кейсы реконструкции таунхаусов и апартаментов",
                            "Relative to Gallery KBNY (Gallery Design Build), unmatched: Strong brand recognition and aggressive digital marketing across Manhattan and Brooklyn",
                            "Relative to Gallery KBNY (Gallery Design Build), unmatched: Full design-build turnkey messaging emphasizing single-point accountability",
                            "Relative to Gallery KBNY (Gallery Design Build), unmatched: Extensive photographic portfolio of completed pre-war and modern apartment renovations"
                        ],
                        "opportunities": [
                            "Bolster (bolster.us) weakness to exploit: Корпоративный конвейерный подход без акцента на эксклюзивную авторскую столярку (bespoke architectural millwork)",
                            "Bolster (bolster.us) weakness to exploit: Меньше гибкости при работе с кастомными материалами и чертежами топовых независимых дизайнеров",
                            "Bolster (bolster.us) weakness to exploit: Фокус на стандартизированные процессы снижает привлекательность для ультра-элитных частных заказчиков",
                            "Gallery KBNY (Gallery Design Build) weakness to exploit: Can feel corporate and volume-driven compared to bespoke artisanal high-touch oversight",
                            "Gallery KBNY (Gallery Design Build) weakness to exploit: Higher overhead costs frequently passed onto clients in change orders",
                            "Gallery KBNY (Gallery Design Build) weakness to exploit: Less tailored white-glove communication for elite architectural interior designer partnerships"
                        ],
                        "threats": [
                            "Bolster (bolster.us) strength to watch: Сильное позиционирование вокруг фиксированной цены и финансовой предсказуемости (Zero Financial Risk)",
                            "Bolster (bolster.us) strength to watch: Мощная цифровая воронка и маркетинг в поисковой выдаче по высокочастотным запросам NYC renovation",
                            "Bolster (bolster.us) strength to watch: Упакованные кейсы реконструкции таунхаусов и апартаментов",
                            "Gallery KBNY (Gallery Design Build) strength to watch: Strong brand recognition and aggressive digital marketing across Manhattan and Brooklyn",
                            "Gallery KBNY (Gallery Design Build) strength to watch: Full design-build turnkey messaging emphasizing single-point accountability",
                            "Gallery KBNY (Gallery Design Build) strength to watch: Extensive photographic portfolio of completed pre-war and modern apartment renovations"
                        ],
                        "is_current": True,
                        "superseded_at": ""
                    }
                }
            ],
            "gap_analysis_results": [],
            "market_research_snapshots": [
                {
                    "id": "0baa8bbe-23c0-468b-a24f-f70bf519ac17",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "industry": "Luxury Residential Renovation & General Contracting (NYC)",
                        "landscape_summary": "Market landscape analysis for industry 'Luxury Residential Renovation & General Contracting (NYC)'.\n\nBrand positioning: White-glove full-gut renovation management with direct principal oversight, meticulous craftsmanship, and frictionless NYC building board navigation..\nTarget segments and competitive landscape are monitored for KS Renovation Group.",
                        "candidate_competitors": [],
                        "sourcing_trail": [],
                        "is_current": True,
                        "superseded_at": ""
                    }
                },
                {
                    "id": "e54e3b3f-86eb-409a-83d4-4ff7c9599afa",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "industry": "Luxury Residential Renovation & General Contracting (NYC)",
                        "landscape_summary": "Market landscape analysis for industry 'Luxury Residential Renovation & General Contracting (NYC)'.\n\nBrand positioning: White-glove full-gut renovation management with direct principal oversight, meticulous craftsmanship, and frictionless NYC building board navigation..\nTarget segments and competitive landscape are monitored for KS Renovation Group.",
                        "candidate_competitors": [],
                        "sourcing_trail": [],
                        "is_current": False,
                        "superseded_at": "2026-11-05T18:29:24.067783+00:00"
                    }
                }
            ],
            "vbs_workspaces": [
                {
                    "id": "6b4f1308-d98c-4479-abf3-8fd8fadee533",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "tenant_id": "default",
                        "owner_id": "imp_u_NBzuhNN-te",
                        "version": 3,
                        "access_model_version": 2,
                        "status": "ready",
                        "created_at": "2026-10-12T16:21:09.419334+00:00",
                        "audit_chain_head": "d59e28f7ff7c3afffb5e8e56e2fe32b2b151c52ad45d75d4125e53239b2be582",
                        "audit_chain_sequence": 3,
                        "audit_chain_started_at": "2026-10-12T16:21:11.257164+00:00",
                        "updated_at": "2026-10-12T16:24:21.915480+00:00"
                    }
                }
            ],
            "visual_brand_systems": [
                {
                    "id": "a5783867-d308-4b6f-b601-5d5b40ae64ca",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "revision": 1,
                        "status": "approved_current",
                        "visual_intent": "Convey quiet luxury, architectural precision, and serene mastery of high-end NYC residential spaces through authentic architectural photography and refined editorial elegance.",
                        "realism_level": "grounded realism",
                        "core_rules": [
                            "Editorial architectural photography with natural daylight and straight vertical lines",
                            "Authentic premium materiality: genuine marble veining, rift-sawn white oak, blackened steel, architectural brass",
                            "Clean, restrained compositions reflecting quiet luxury and meticulous craftsmanship",
                            "True NYC pre-war, brownstone, and luxury condo architectural context"
                        ],
                        "prohibited_patterns": [
                            "Hyper-saturated or plastic AI textures",
                            "Cluttered or dirty job sites without professional protection",
                            "Generic stock 3D renders with unrealistic lighting and fake furniture",
                            "Aggressive marketing badges, garish discount stickers, or loud promotional overlays"
                        ],
                        "change_note": "Initial VBS baseline draft established from KSR master brand guidelines.",
                        "created_by": "imp_u_NBzuhNN-te",
                        "tenant_id": "default",
                        "supersedes_vbs_id": "",
                        "created_at": "2026-10-12T16:21:36.885801+00:00",
                        "approved_at": "2026-10-12T16:24:23.806210+00:00",
                        "approval_note": "Утверждена базовая архитектурно-визуальная система KS Renovation Group (VBS v1): премиальный нью-йоркский интерьерный реализм, прецизионная столярка AWI, чистые архитектурные ракурсы и отсутствие искусственного стокового лоска.",
                        "approval_evidence_snapshot": [],
                        "approval_evidence_snapshot_hash": "9941ddeb1f8391782b88742140faac49d700e3cf08dada38ba56df863b26fc1f",
                        "approval_evidence_workspace_version": 3,
                        "approval_audit_event_id": "ad2ab28b-6a2b-4fca-9ae4-5a7d04fbb94d",
                        "approval_audit_chain_sequence": 3
                    }
                }
            ],
            "visual_evidence": [],
            "visual_profiles": [],
            "vbs_brand_memberships": [
                {
                    "id": "95b13fd2-1cdc-4266-8d35-3380277f9968",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "tenant_id": "default",
                        "user_id": "imp_u_NBzuhNN-te",
                        "role": "owner",
                        "status": "active",
                        "created_by": "imp_u_NBzuhNN-te",
                        "created_at": "2026-10-12T16:21:10.079087+00:00"
                    }
                }
            ],
            "visual_brand_audit_events": [
                {
                    "id": "ad2ab28b-6a2b-4fca-9ae4-5a7d04fbb94d",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "vbs_id": "a5783867-d308-4b6f-b601-5d5b40ae64ca",
                        "event_type": "vbs_approved_current",
                        "actor_id": "imp_u_NBzuhNN-te",
                        "tenant_id": "default",
                        "details": "Утверждена базовая архитектурно-визуальная система KS Renovation Group (VBS v1): премиальный нью-йоркский интерьерный реализм, прецизионная столярка AWI, чистые архитектурные ракурсы и отсутствие искусственного стокового лоска.",
                        "occurred_at": "2026-10-12T16:24:25.126001+00:00",
                        "chain_sequence": 3,
                        "previous_integrity_hash": "4eb345624a4f0a2ff20d51d0f3bd6fc185f8664a792af055ee24ca6b5a8e685e",
                        "immutable_metadata": {
                            "approval_evidence_snapshot_hash": "9941ddeb1f8391782b88742140faac49d700e3cf08dada38ba56df863b26fc1f",
                            "approval_evidence_count": 0,
                            "vbs_revision": 1,
                            "workspace_version": 3
                        },
                        "integrity_hash": "d59e28f7ff7c3afffb5e8e56e2fe32b2b151c52ad45d75d4125e53239b2be582",
                        "integrity_version": 3
                    }
                },
                {
                    "id": "bf0a4fe6-de93-43af-bbe9-5b607a532869",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "vbs_id": "a5783867-d308-4b6f-b601-5d5b40ae64ca",
                        "event_type": "vbs_draft_created",
                        "actor_id": "imp_u_NBzuhNN-te",
                        "tenant_id": "default",
                        "details": "Created revision 1 as a draft.",
                        "occurred_at": "2026-10-12T16:21:38.005508+00:00",
                        "chain_sequence": 2,
                        "previous_integrity_hash": "fe03bb69014c160e1162ca11e383507ae7b0f95704dfd4252872d6922200407a",
                        "immutable_metadata": {},
                        "integrity_hash": "4eb345624a4f0a2ff20d51d0f3bd6fc185f8664a792af055ee24ca6b5a8e685e",
                        "integrity_version": 2
                    }
                },
                {
                    "id": "c6abfbeb-1f1c-44b1-a48e-625896ae8fc4",
                    "data": {
                        "brand_id": "6e122b5c-1d89-4b34-bb14-de33a1689d7a",
                        "vbs_id": "",
                        "event_type": "workspace_initialized",
                        "actor_id": "imp_u_NBzuhNN-te",
                        "tenant_id": "default",
                        "details": "Explicit owner claim created the P0 VBS workspace.",
                        "occurred_at": "2026-10-12T16:21:11.257164+00:00",
                        "chain_sequence": 1,
                        "previous_integrity_hash": "",
                        "immutable_metadata": {},
                        "integrity_hash": "fe03bb69014c160e1162ca11e383507ae7b0f95704dfd4252872d6922200407a",
                        "integrity_version": 2
                    }
                }
            ],
            "visual_brand_audit_integrity_incidents": [],
            "vbs_media_conformance": []
        },
        "exported_at": "2026-11-11T12:11:22.120078+00:00",
        "total_records": 16
    }

    raw_json = json.dumps(user_payload)
    ctx = MockContext(user_id="imp_u_NBzuhNN-te", tenant_id="tenant-ksr-new")
    res = await import_brand_project(ctx, ImportBrandProjectParams(json_data=raw_json))
    assert res.status == "success"
    b_id = res.data.brand_id
    assert b_id == "6e122b5c-1d89-4b34-bb14-de33a1689d7a"

    # Verify brand profile
    bp = await ctx.store.get("brand_profiles", b_id)
    assert bp is not None
    assert bp.data["brand_name"] == "KS Renovation Group"

    # Verify competitor profiles
    comps = await ctx.store.query("competitor_profiles", where={"brand_id": b_id})
    assert len(comps.data) == 2

    # Verify target segments
    segs = await ctx.store.query("target_segments", where={"brand_id": b_id})
    assert len(segs.data) == 4

    # Verify swot results
    swots = await ctx.store.query("swot_results", where={"brand_id": b_id})
    assert len(swots.data) == 1

    # Verify market research
    mrs = await ctx.store.query("market_research_snapshots", where={"brand_id": b_id})
    assert len(mrs.data) == 2

    # Verify visual brand systems
    vbs = await ctx.store.query("visual_brand_systems", where={"brand_id": b_id})
    assert len(vbs.data) == 1

    # Verify visual brand workspace
    ws = await ctx.store.query("vbs_workspaces", where={"brand_id": b_id})
    assert len(ws.data) == 1
@pytest.mark.asyncio
async def test_import_deduplication():
    """Verify that importing JSON multiple times or when brand exists by site_id/name does not create duplicates."""
    payload = {
        "format": "imperal:brand_project_export:v1",
        "brand_id": "test-dedup-id-1",
        "brand_profile": {
            "id": "test-dedup-id-1",
            "data": {
                "site_id": "dedup-test.com",
                "brand_name": "Dedup Test Brand",
                "mission": "Original mission",
            }
        },
        "collections": {}
    }
    raw_json = json.dumps(payload)
    ctx = MockContext(user_id="imp_u_test", tenant_id="tenant-dedup")

    # First import
    res1 = await import_brand_project(ctx, ImportBrandProjectParams(json_data=raw_json))
    assert res1.status == "success"

    all_brands_1 = await ctx.store.query("brand_profiles")
    assert len(all_brands_1.data) == 1
    assert all_brands_1.data[0].data["brand_name"] == "Dedup Test Brand"

    # Second import with same JSON
    res2 = await import_brand_project(ctx, ImportBrandProjectParams(json_data=raw_json))
    assert res2.status == "success"

    all_brands_2 = await ctx.store.query("brand_profiles")
    assert len(all_brands_2.data) == 1, "Duplicate brand profile was created on re-import"

    # Third import with different exported ID but matching site_id
    payload_diff_id = {
        "format": "imperal:brand_project_export:v1",
        "brand_id": "different-exported-id",
        "brand_profile": {
            "id": "different-exported-id",
            "data": {
                "site_id": "dedup-test.com",
                "brand_name": "Dedup Test Brand",
                "mission": "Updated mission",
            }
        },
        "collections": {}
    }
    res3 = await import_brand_project(ctx, ImportBrandProjectParams(json_data=json.dumps(payload_diff_id)))
    assert res3.status == "success"

    all_brands_3 = await ctx.store.query("brand_profiles")
    assert len(all_brands_3.data) == 1, "Brand duplicated despite matching site_id"
    assert all_brands_3.data[0].data["mission"] == "Updated mission"
