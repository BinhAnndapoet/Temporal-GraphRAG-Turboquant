"""Querying operations for temporal knowledge graphs.

This module contains functions for querying temporal knowledge graphs including
local queries, global queries, naive RAG queries, and related retrieval operations.
"""

from __future__ import annotations

import re
import json
import sys
import asyncio
from typing import Dict, List, Union, Optional, Any
from collections import Counter, defaultdict
import logging

# Import from new modules
from ..config.prompts import get_prompt_manager, GRAPH_FIELD_SEP
from ..temporal.operations import (
    enhanced_infer_timestamp_level,
    enhanced_normalize_timestamp,
    temporal_overlap,
    extract_year,
    extract_quarter,
    calculate_temporal_distance,
)
from ..utils.hashing import compute_mdhash_id
from ..utils.json_utils import convert_response_to_json
from ..utils.helpers import (
    logger,
    clean_str,
    split_string_by_multi_markers,
    list_of_list_to_csv,
    truncate_list_by_token_size,
    sort_timestamp_by_datetime,
    convert_timestamp_to_datetime,
)
from ..core.building import (
    handle_single_timestamp_extraction as _handle_single_timestamp_extraction,
    find_timestamp_in_hierarchy as _find_timestamp_in_hierarchy,
)

# Import centralized temporal normalizer
from ..temporal.normalization import get_temporal_normalizer

# Import storage base classes
from ..storage.base import (
    BaseGraphStorage,
    BaseVectorStorage,
    BaseKVStorage,
)

# Import schema types from core.types
from ..core.types import (
    QueryParam,
    TemporalSchema,
    TextChunkSchema,
    SingleTemporalSchema,
)

# Get prompt manager instance
_prompt_manager = None

def _get_prompts():
    """Get prompts dict from PromptManager."""
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = get_prompt_manager()
    return _prompt_manager.prompts

# Create PROMPTS alias for backward compatibility during migration
class _PromptsProxy:
    def __getitem__(self, key):
        return _get_prompts()[key]
    def get(self, key, default=None):
        return _get_prompts().get(key, default)
    def __contains__(self, key):
        return key in _get_prompts()
    def keys(self):
        return _get_prompts().keys()
    def values(self):
        return _get_prompts().values()
    def items(self):
        return _get_prompts().items()

PROMPTS = _PromptsProxy()

# Import CommunitySchema for type hints
from ..core.types import CommunitySchema as CommunitySchemaType

# Helper function: merge edges round robin
def merge_edges_round_robin(entity_edge_lists: list[list[dict]], top_k: int) -> list[dict]:
    merged_edges = []
    seen_edges = set()
    pointers = [0] * len(entity_edge_lists)
    total_entities = len(entity_edge_lists)

    while len(merged_edges) < top_k:
        progress_made = False
        for i in range(total_entities):
            edge_list = entity_edge_lists[i]
            while pointers[i] < len(edge_list):
                edge = edge_list[pointers[i]]
                pointers[i] += 1

                # Safety check for edge and src_tgt
                if edge is None or not isinstance(edge, dict) or "src_tgt" not in edge:
                    logger.warning(f"Skipping invalid edge: {edge}")
                    continue

                edge_key = tuple(sorted(edge["src_tgt"]))
                if edge_key not in seen_edges:
                    seen_edges.add(edge_key)
                    merged_edges.append(edge)
                    progress_made = True
                    break  # move to next entity
        if not progress_made:
            break  # all exhausted or all remaining are duplicates

    return merged_edges


# Helper function: create ranking config
def create_ranking_config(
    query_type: str = "general",
    temporal_focus: bool = True,
    custom_weights: dict = None
) -> dict:
    """
    Create ranking configuration based on query type and preferences.
    """
    base_configs = {
        "general": {
            'temporal_alignment': 0.3,
            'temporal_proximity': 0.2,
            'node_degree': 0.3,
            'query_relevance': 0.2
        },
        "temporal": {
            'temporal_alignment': 0.5,
            'temporal_proximity': 0.3,
            'node_degree': 0.15,
            'query_relevance': 0.05
        },
        "enumeration": {
            'temporal_alignment': 0.25,
            'temporal_proximity': 0.2,
            'node_degree': 0.25,
            'query_relevance': 0.3
        },
        "comparison": {
            'temporal_alignment': 0.35,
            'temporal_proximity': 0.25,
            'node_degree': 0.25,
            'query_relevance': 0.15
        }
    }
    
    config = base_configs.get(query_type, base_configs["general"]).copy()
    
    if temporal_focus:
        config['temporal_alignment'] = min(config['temporal_alignment'] * 1.2, 0.6)
        config['temporal_proximity'] = min(config['temporal_proximity'] * 1.1, 0.4)
        total_temporal = config['temporal_alignment'] + config['temporal_proximity']
        remaining_weight = 1.0 - total_temporal
        if remaining_weight > 0:
            config['node_degree'] = remaining_weight * 0.6
            config['query_relevance'] = remaining_weight * 0.4
    
    if custom_weights:
        for key, value in custom_weights.items():
            if key in config:
                config[key] = value
    
    total_weight = sum(config.values())
    if total_weight > 0:
        config = {k: v / total_weight for k, v in config.items()}
    
    return config


# Helper function: get entities from temporal subgraph
async def _get_entities_from_temporal_subgraph(timestamps: list[str],
                                               temporal_hierarchy: dict[str, SingleTemporalSchema]):
    entities = []
    logger.info(f"Getting entities from temporal subgraph for timestamps: {timestamps}")
    
    for timestamp in timestamps:
        found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
        if found:
            timestamp_data = temporal_hierarchy[matched_key]
            if 'nodes' in timestamp_data:
                entities.extend(timestamp_data['nodes'])
                logger.info(f"Found {len(timestamp_data['nodes'])} entities for timestamp {timestamp} -> {matched_key}")
            else:
                logger.warning(f"No nodes found for timestamp {timestamp} -> {matched_key}")
        else:
            logger.warning(f"Timestamp {timestamp} not found in temporal hierarchy")
    
    unique_entities = []
    seen = set()
    for entity in entities:
        if entity not in seen:
            unique_entities.append(entity)
            seen.add(entity)
    
    logger.info(f"Total unique entities in temporal subgraph: {len(unique_entities)}")
    return unique_entities


# Helper function: get broader temporal entities
async def _get_broader_temporal_entities(timestamps: list[str],
                                        temporal_hierarchy: dict[str, SingleTemporalSchema]):
    entities = []
    logger.info(f"Getting broader temporal entities for timestamps: {timestamps}")
    
    years = set()
    for timestamp in timestamps:
        if isinstance(timestamp, str):
            if timestamp.isdigit() and len(timestamp) == 4:
                years.add(timestamp)
            elif '-' in timestamp:
                year_part = timestamp.split('-')[0]
                if year_part.isdigit() and len(year_part) == 4:
                    years.add(year_part)
    
    for year in years:
        related_timestamps = [ts for ts in temporal_hierarchy.keys() if year in ts]
        for ts in related_timestamps:
            found, matched_key = _find_timestamp_in_hierarchy(ts, temporal_hierarchy)
            if found:
                timestamp_data = temporal_hierarchy[matched_key]
                if 'nodes' in timestamp_data:
                    entities.extend(timestamp_data['nodes'])
                    logger.info(f"Found {len(timestamp_data['nodes'])} entities for broader timestamp {ts}")
    
    unique_entities = []
    seen = set()
    for entity in entities:
        if entity not in seen:
            unique_entities.append(entity)
            seen.add(entity)
    
    logger.info(f"Total unique entities in broader temporal context: {len(unique_entities)}")
    return unique_entities


# Helper function: calculate temporal aware rank
async def calculate_temporal_aware_rank(
    entity: dict,
    query_timestamps: list[str],
    temporal_hierarchy: dict[str, SingleTemporalSchema],
    node_degree: int,
    query: str = None,
    ranking_weights: dict = None,
    embedding_func = None
) -> float:
    default_weights = {
        'temporal_alignment': 0.4,
        'temporal_proximity': 0.3,
        'node_degree': 0.2,
        'query_relevance': 0.1
    }
    
    weights = ranking_weights if ranking_weights else default_weights
    
    if not query_timestamps:
        return min(node_degree / 100.0, 1.0)
    
    temporal_alignment = 0.0
    entity_timestamps = set()
    
    if 'source_id' in entity:
        source_id = entity['source_id']
        if isinstance(source_id, dict):
            entity_timestamps.update(source_id.keys())
        elif isinstance(source_id, str):
            timestamp_patterns = [
                r'\b\d{4}\b',
                r'\b\d{4}-\d{2}\b',
                r'\b\d{4}-\d{2}-\d{2}\b',
                r'\b\d{4}Q[1-4]\b',
            ]
            for pattern in timestamp_patterns:
                matches = re.findall(pattern, source_id)
                entity_timestamps.update(matches)
    
    for query_ts in query_timestamps:
        for entity_ts in entity_timestamps:
            if temporal_overlap(query_ts, entity_ts):
                temporal_alignment += 1.0
                break
    
    temporal_score = min(temporal_alignment / len(query_timestamps), 1.0)
    
    temporal_proximity = 0.0
    if temporal_alignment > 0:
        proximity_scores = []
        for query_ts in query_timestamps:
            min_distance = float('inf')
            for entity_ts in entity_timestamps:
                distance = calculate_temporal_distance(query_ts, entity_ts)
                min_distance = min(min_distance, distance)
            if min_distance != float('inf'):
                proximity_score = max(0, 1.0 - (min_distance / 10.0))
                proximity_scores.append(proximity_score)
        
        if proximity_scores:
            temporal_proximity = sum(proximity_scores) / len(proximity_scores)
    
    normalized_degree = min(node_degree / 100.0, 1.0)
    
    query_relevance = 0.0
    if query and 'entity_name' in entity:
        entity_name = entity['entity_name']
        
        if embedding_func:
            try:
                import numpy as np
                from sklearn.metrics.pairwise import cosine_similarity
                
                query_embedding = await embedding_func([query])
                entity_embedding = await embedding_func([entity_name])
                
                if query_embedding.ndim == 1:
                    query_embedding = query_embedding.reshape(1, -1)
                if entity_embedding.ndim == 1:
                    entity_embedding = entity_embedding.reshape(1, -1)
                
                similarity = cosine_similarity(query_embedding, entity_embedding)[0][0]
                query_relevance = max(0.0, similarity)
                logger.debug(f"Cosine similarity for '{entity_name}' vs query: {similarity:.3f}")
                
            except Exception as e:
                logger.warning(f"Failed to calculate cosine similarity: {e}, falling back to keyword matching")
                query_lower = query.lower()
                entity_lower = entity_name.lower()
                
                if entity_lower in query_lower or query_lower in entity_lower:
                    query_relevance = 1.0
                elif any(word in entity_lower for word in query_lower.split()):
                    query_relevance = 0.5
        else:
            query_lower = query.lower()
            entity_lower = entity_name.lower()
            
            if entity_lower in query_lower or query_lower in entity_lower:
                query_relevance = 1.0
            elif any(word in entity_lower for word in query_lower.split()):
                query_relevance = 0.5
    
    final_rank = (
        temporal_score * weights['temporal_alignment'] +
        temporal_proximity * weights['temporal_proximity'] +
        normalized_degree * weights['node_degree'] +
        query_relevance * weights['query_relevance']
    )
    
    return final_rank


# Helper function: calculate temporal aware edge rank
async def calculate_temporal_aware_edge_rank(
    edge: dict,
    query_timestamps: list[str],
    temporal_hierarchy: dict[str, SingleTemporalSchema],
    edge_degree: int,
    weight: float = 0.0,
    query: str = None,
    ranking_weights: dict = None,
    embedding_func = None
) -> float:
    default_weights = {
        'temporal_alignment': 0.35,
        'temporal_proximity': 0.15,
        'edge_degree': 0.05,
        'edge_weight': 0.15,
        'query_relevance': 0.35
    }
    
    weights = ranking_weights if ranking_weights else default_weights
    
    if not query_timestamps:
        normalized_degree = min(edge_degree / 100.0, 1.0)
        normalized_weight = min(weight / 10.0, 1.0)
        return (normalized_degree * 0.7) + (normalized_weight * 0.3)
    
    temporal_alignment = 0.0
    edge_timestamps = set()
    
    if 'source_id' in edge:
        source_id = edge['source_id']
        if isinstance(source_id, dict):
            edge_timestamps.update(source_id.keys())
        elif isinstance(source_id, str):
            timestamp_patterns = [
                r'\b\d{4}\b',
                r'\b\d{4}-\d{2}\b',
                r'\b\d{4}-\d{2}-\d{2}\b',
                r'\b\d{4}Q[1-4]\b',
            ]
            for pattern in timestamp_patterns:
                matches = re.findall(pattern, source_id)
                edge_timestamps.update(matches)
    
    for query_ts in query_timestamps:
        for edge_ts in edge_timestamps:
            if temporal_overlap(query_ts, edge_ts):
                temporal_alignment += 1.0
                break
    
    temporal_score = min(temporal_alignment / len(query_timestamps), 1.0)
    
    temporal_proximity = 0.0
    if temporal_alignment > 0:
        proximity_scores = []
        for query_ts in query_timestamps:
            min_distance = float('inf')
            for edge_ts in edge_timestamps:
                distance = calculate_temporal_distance(query_ts, edge_ts)
                min_distance = min(min_distance, distance)
            if min_distance != float('inf'):
                proximity_score = max(0, 1.0 - (min_distance / 10.0))
                proximity_scores.append(proximity_score)
        
        if proximity_scores:
            temporal_proximity = sum(proximity_scores) / len(proximity_scores)
    
    normalized_degree = min(edge_degree / 100.0, 1.0)
    normalized_weight = min(weight / 10.0, 1.0)
    
    query_relevance = 0.0
    if query and 'description' in edge:
        edge_description = edge['description']
        
        if embedding_func:
            try:
                import numpy as np
                from sklearn.metrics.pairwise import cosine_similarity
                
                query_embedding = await embedding_func([query])
                edge_embedding = await embedding_func([edge_description])
                
                if query_embedding.ndim == 1:
                    query_embedding = query_embedding.reshape(1, -1)
                if entity_embedding.ndim == 1:
                    entity_embedding = entity_embedding.reshape(1, -1)
                
                similarity = cosine_similarity(query_embedding, edge_embedding)[0][0]
                query_relevance = max(0.0, similarity)
                logger.debug(f"Edge cosine similarity vs query: {similarity:.3f}")
                
            except Exception as e:
                logger.warning(f"Failed to calculate edge cosine similarity: {e}, falling back to keyword matching")
                query_lower = query.lower()
                description_lower = edge_description.lower()
                
                if description_lower in query_lower or query_lower in description_lower:
                    query_relevance = 1.0
                elif any(word in description_lower for word in query_lower.split()):
                    query_relevance = 0.5
        else:
            query_lower = query.lower()
            description_lower = edge_description.lower()
            
            if description_lower in query_lower or query_lower in description_lower:
                query_relevance = 1.0
            elif any(word in description_lower for word in query_lower.split()):
                query_relevance = 0.5
    
    final_rank = (
        temporal_score * weights['temporal_alignment'] +
        temporal_proximity * weights['temporal_proximity'] +
        normalized_degree * weights['edge_degree'] +
        normalized_weight * weights['edge_weight'] +
        query_relevance * weights['query_relevance']
    )
    
    return final_rank


# Helper function: find most related community from entities
async def _find_most_related_community_from_entities(
        node_datas: list[dict],
        query_param: QueryParam,
        community_reports: BaseKVStorage[TemporalSchema],
):
    related_communities = []
    for node_d in node_datas:
        if "clusters" not in node_d:
            continue
        related_communities.extend(json.loads(node_d["clusters"]))
    related_community_dup_keys = [
        str(dp["cluster"])
        for dp in related_communities
        if dp["level"] <= query_param.level
    ]
    related_community_keys_counts = dict(Counter(related_community_dup_keys))
    _related_community_datas = await asyncio.gather(
        *[community_reports.get_by_id(k) for k in related_community_keys_counts.keys()]
    )
    related_community_datas = {
        k: v
        for k, v in zip(related_community_keys_counts.keys(), _related_community_datas)
        if v is not None
    }
    related_community_keys = sorted(
        related_community_keys_counts.keys(),
        key=lambda k: (
            related_community_keys_counts[k],
            related_community_datas[k]["report_json"].get("rating", -1),
        ),
        reverse=True,
    )
    sorted_community_datas = [
        related_community_datas[k] for k in related_community_keys
    ]

    use_community_reports = truncate_list_by_token_size(
        sorted_community_datas,
        key=lambda x: x["report_string"],
        max_token_size=query_param.local_max_token_for_community_report,
    )
    if query_param.local_community_single_one:
        use_community_reports = use_community_reports[:1]
    return use_community_reports


# Helper function: find most related text unit from entities
async def _find_most_related_text_unit_from_entities(
        node_datas: list[dict],
        query_param: QueryParam,
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        knowledge_graph_inst: BaseGraphStorage,
):
    text_units = [
        split_string_by_multi_markers(dp["source_id"], [GRAPH_FIELD_SEP])
        for dp in node_datas
    ]
    edges = await asyncio.gather(
        *[knowledge_graph_inst.get_node_edges(dp["entity_name"]) for dp in node_datas]
    )
    all_one_hop_nodes = set()
    for this_edges in edges:
        if not this_edges:
            continue
        all_one_hop_nodes.update([e[1] for e in this_edges])
    all_one_hop_nodes = list(all_one_hop_nodes)
    all_one_hop_nodes_data = await asyncio.gather(
        *[knowledge_graph_inst.get_node(e) for e in all_one_hop_nodes]
    )
    all_one_hop_nodes = [k for k, v in zip(all_one_hop_nodes, all_one_hop_nodes_data) if
                         v and v['entity_type'].lower() not in PROMPTS['DEFAULT_TEMPORAL_HIERARCHY']]

    all_one_hop_nodes_data = [n for n in all_one_hop_nodes_data if
                              n and n['entity_type'].lower() not in PROMPTS['DEFAULT_TEMPORAL_HIERARCHY']]
    all_one_hop_text_units_lookup = {
        k: set(split_string_by_multi_markers(v["source_id"], [GRAPH_FIELD_SEP]))
        for k, v in zip(all_one_hop_nodes, all_one_hop_nodes_data)
        if v
    }
    all_text_units_lookup = {}
    for index, (this_text_units, this_edges) in enumerate(zip(text_units, edges)):
        for c_id in this_text_units:
            if c_id in all_text_units_lookup:
                continue
            relation_counts = 0
            for e in this_edges:
                if (
                        e[1] in all_one_hop_text_units_lookup
                        and c_id in all_one_hop_text_units_lookup[e[1]]
                ):
                    relation_counts += 1
            all_text_units_lookup[c_id] = {
                "data": await text_chunks_db.get_by_id(c_id),
                "order": index,
                "relation_counts": relation_counts,
            }
    if any([v is None for v in all_text_units_lookup.values()]):
        logger.warning("Text chunks are missing, maybe the storage is damaged")
    all_text_units = [
        {"id": k, **v} for k, v in all_text_units_lookup.items() if v is not None
    ]
    all_text_units = sorted(
        all_text_units, key=lambda x: (x["order"], -x["relation_counts"])
    )
    all_text_units = truncate_list_by_token_size(
        all_text_units,
        key=lambda x: x["data"]["content"],
        max_token_size=query_param.local_max_token_for_text_unit,
    )
    all_text_units: list[TextChunkSchema] = [t["data"] for t in all_text_units]
    return all_text_units


# Helper function: find most related temporal text unit from entities
async def _find_most_related_temporal_text_unit_from_entities(
        node_datas: list[dict],
        query_param: QueryParam,
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        knowledge_graph_inst: BaseGraphStorage,
        timestamps: list[str],
):
    if not timestamps:
        logger.info("No timestamps available, falling back to non-temporal text unit search")
        return await _find_most_related_text_unit_from_entities(node_datas, query_param, text_chunks_db, knowledge_graph_inst)
    
    all_chunk_ids = []
    for node_data in node_datas:
        if node_data.get("source_id"):
            chunk_ids = split_string_by_multi_markers(node_data["source_id"], [GRAPH_FIELD_SEP])
            all_chunk_ids.extend(chunk_ids)
    
    if not all_chunk_ids:
        logger.warning("No chunk IDs found in node data")
        return []
    
    all_related_text_units = await asyncio.gather(
        *[text_chunks_db.get_by_id(chunk_id) for chunk_id in all_chunk_ids]
    )
    
    valid_text_units = [unit for unit in all_related_text_units if unit is not None]
    if valid_text_units:
        logger.info(f"\n\nall_related_text_units[0]: {valid_text_units[0].keys()}\n\n")
    else:
        logger.warning("No valid text units found")
        return []
    all_text_units = []
    seen = set()

    for chunk_id, text_unit in zip(all_chunk_ids, all_related_text_units):
        if text_unit and chunk_id not in seen:
            text_unit_with_id = {**text_unit, "id": chunk_id}
            seen.add(chunk_id)
            all_text_units.append(text_unit_with_id)

    if not all_text_units:
        logger.warning("No text units found")
        return []

    all_text_units_data = []
    for t_d in all_text_units:
        for ts in timestamps:
            new_text_unit_dict = {
                "id": t_d["id"],
                "content": f"Content from {ts}: {t_d['content']}",
                "source_id": t_d.get("source_id", ""),
                "tokens": t_d.get("tokens", 0),
                "full_doc_id": t_d.get("full_doc_id", ""),
                "chunk_order_index": t_d.get("chunk_order_index", 0)
            }
            all_text_units_data.append(new_text_unit_dict)

    all_text_units_data = sorted(
        all_text_units_data, key=lambda x: x.get("chunk_order_index", 0)
    )
    
    all_text_units_data = truncate_list_by_token_size(
        all_text_units_data,
        key=lambda x: x["content"],
        max_token_size=query_param.local_max_token_for_text_unit,
    )
    return all_text_units_data


# Helper function: find most related edges from entities
async def _find_most_related_edges_from_entities(
        node_datas: list[dict],
        query_param: QueryParam,
        knowledge_graph_inst: BaseGraphStorage,
        aligned_timestamp_in_query: list[str] = None,
        temporal_hierarchy: dict[str, SingleTemporalSchema] = None,
        query: str = None,
):
    all_related_edges = await asyncio.gather(
        *[knowledge_graph_inst.get_node_edges(dp["entity_name"]) for dp in node_datas]
    )

    all_edges = []
    seen = set()

    for this_edges in all_related_edges:
        if this_edges is None:
            continue
        for e in this_edges:
            sorted_edge = tuple(sorted(e))
            if sorted_edge not in seen:
                seen.add(sorted_edge)
                all_edges.append(sorted_edge)

    all_edges_pack = await asyncio.gather(
        *[knowledge_graph_inst.get_edge(e[0], e[1]) for e in all_edges]
    )
    all_edges_degree = await asyncio.gather(
        *[knowledge_graph_inst.edge_degree(e[0], e[1]) for e in all_edges]
    )
    all_edges_data = []
    for k, v, d in zip(all_edges, all_edges_pack, all_edges_degree):
        if v is not None:
            if aligned_timestamp_in_query and temporal_hierarchy:
                rank = await calculate_temporal_aware_edge_rank(
                    v,
                    aligned_timestamp_in_query,
                    temporal_hierarchy,
                    d,
                    v.get("weight", 0),
                    query
                )
            else:
                rank = d
            
            all_edges_data.append({
                "src_tgt": k, 
                "rank": rank, 
                "weight": v.get("weight", 0), 
                **v
            })
    
    for edge_data in all_edges_data:
        if isinstance(edge_data.get("description"), dict):
            desc_parts = []
            for ts, desc in edge_data["description"].items():
                desc_parts.append(f"{ts}: {desc}")
            edge_data["description"] = "; ".join(desc_parts)
        elif not isinstance(edge_data.get("description"), str):
            edge_data["description"] = str(edge_data.get("description", ""))
    
    all_edges_data = sorted(
        all_edges_data, key=lambda x: (x["rank"], x["weight"]), reverse=True
    )
    all_edges_data = truncate_list_by_token_size(
        all_edges_data,
        key=lambda x: x.get("description", "UNKNOWN"),
        max_token_size=query_param.local_max_token_for_local_context,
    )
    return all_edges_data


# Helper function: find most related temporal edges from entities
async def _find_most_related_temporal_edges_from_entities(
        node_datas: list[dict],
        query_param: QueryParam,
        knowledge_graph_inst: BaseGraphStorage,
        timestamps: list[str],
        top_k: int,
        temporal_hierarchy: dict[str, SingleTemporalSchema] = None,
        query: str = None
):
    if not timestamps:
        logger.info("No timestamps available, falling back to non-temporal edge search")
        return await _find_most_related_edges_from_entities(node_datas, query_param, knowledge_graph_inst, None, None, None)
    
    entity_edge_lists = []
    for node_data in node_datas:
        entity_edges = await knowledge_graph_inst.get_temporal_edges(
            node_data["entity_name"], timestamps, top_k=top_k
        )
        entity_edge_lists.append(entity_edges)
    
    merged_edges = merge_edges_round_robin(entity_edge_lists, top_k)
    
    for edge_data in merged_edges:
        if isinstance(edge_data.get("description"), dict):
            desc_parts = []
            for ts, desc in edge_data["description"].items():
                desc_parts.append(f"{ts}: {desc}")
            edge_data["description"] = "; ".join(desc_parts)
        elif not isinstance(edge_data.get("description"), str):
            edge_data["description"] = str(edge_data.get("description", ""))
    
    return merged_edges


# Helper function: find most related temporal edges from entities topk merged
async def _find_most_related_temporal_edges_from_entities_topk_merged(
        node_datas: list[dict],
        query_param: QueryParam,
        knowledge_graph_inst: BaseGraphStorage,
        timestamps: list[str],
        top_k: int,
        temporal_hierarchy: dict[str, SingleTemporalSchema] = None,
        query: str = None
):
    if not timestamps:
        logger.info("No timestamps available, falling back to non-temporal edge search")
        return await _find_most_related_edges_from_entities(node_datas, query_param, knowledge_graph_inst, None, None, None)
    
    all_temporal_edges_data = []
    entity_sorted_edges = []
    for dp in node_datas:
        entity_name = dp["entity_name"]

        edges = await knowledge_graph_inst.get_node_edges(entity_name)
        if edges is None:
            continue

        seen = set()
        unique_edges = []
        for e in edges:
            sorted_edge = tuple(sorted(e))
            if sorted_edge not in seen:
                seen.add(sorted_edge)
                unique_edges.append(sorted_edge)

        edge_packs = await asyncio.gather(
            *[knowledge_graph_inst.get_edge(e[0], e[1]) for e in unique_edges]
        )
        filtered_edge_packs = [e for e in edge_packs if e and e.get("description")]
        filtered_edges = [e for e_data, e in zip(edge_packs, unique_edges) if e_data and e_data.get("description")]

        edge_degrees = await asyncio.gather(
            *[knowledge_graph_inst.edge_degree(e[0], e[1]) for e in filtered_edges]
        )

        edge_data = []
        for e, data, d in zip(filtered_edges, filtered_edge_packs, edge_degrees):
            rank = await calculate_temporal_aware_edge_rank(
                data,
                timestamps,
                temporal_hierarchy or {},
                d,
                data.get("weight", 0),
                query
            )
            edge_data.append({
                "src_tgt": e, 
                "rank": rank, 
                "weight": data.get("weight", 0), 
                **data
            })

        edge_data = sorted(edge_data, key=lambda x: x["rank"], reverse=True)
        entity_sorted_edges.append(edge_data)

    merged_edges = merge_edges_round_robin(entity_sorted_edges, top_k=20)
    for e_d in merged_edges:
        if timestamps:
            for ts in timestamps:
                if isinstance(e_d.get("description"), dict):
                    if e_d["description"].get(ts):
                        all_temporal_edges_data.append({
                            **{k: v for k, v in e_d.items() if k not in ["description", "source_id"]},
                            "description": f"description in {ts}, {e_d['description'].get(ts)}",
                            "source_id": (e_d.get("source_id") or {}).get(ts, ""),
                        })
                elif isinstance(e_d.get("description"), str):
                    if ts.lower() in e_d["description"].lower():
                        all_temporal_edges_data.append({
                            **{k: v for k, v in e_d.items() if k not in ["description", "source_id"]},
                            "description": f"description in {ts}, {e_d['description']}",
                            "source_id": e_d.get("source_id", ""),
                        })
        else:
            if isinstance(e_d.get("description"), dict):
                for ts, desc in e_d["description"].items():
                    if desc:
                        all_temporal_edges_data.append({
                            **{k: v for k, v in e_d.items() if k not in ["description", "source_id"]},
                            "description": f"description in {ts}, {desc}",
                            "source_id": (e_d.get("source_id") or {}).get(ts, ""),
                        })
            elif isinstance(e_d.get("description"), str) and e_d["description"]:
                all_temporal_edges_data.append({
                    **{k: v for k, v in e_d.items() if k not in ["description", "source_id"]},
                    "description": e_d["description"],
                    "source_id": e_d.get("source_id", ""),
                })

    return all_temporal_edges_data


# Helper function: find most related temporal community from entities
async def _find_most_related_temporal_community_from_entities(
        query_param: QueryParam,
        community_reports: BaseKVStorage[TemporalSchema],
        timestamps: list[str],
):
    if not timestamps:
        logger.info("No timestamps available, falling back to non-temporal community search")
        return []
    
    temporal_community_reports = await asyncio.gather(
        *[community_reports.get_by_id(ts) for ts in timestamps]
    )

    temporal_community_reports = [report for report in temporal_community_reports if report is not None]

    if not temporal_community_reports:
        logger.warning("No temporal community reports found for the given timestamps")
        return []

    sorted_community_reports = sorted(
        temporal_community_reports,
        key=lambda x: (
            x["report_json"].get("rating", 0),
            len(x.get("temporal_edges", [])) + len(x.get("nodes", []))
        ),
        reverse=True,
    )

    use_community_reports = truncate_list_by_token_size(
        sorted_community_reports,
        key=lambda x: x["report_string"],
        max_token_size=query_param.local_max_token_for_community_report,
    )
    
    if query_param.local_community_single_one:
        use_community_reports = use_community_reports[:1]
    
    return use_community_reports


# Helper function: retrieve timestamp
async def _retrieve_timestamp(
        query,
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        global_config: dict, ):
    use_llm_func: callable = global_config["best_model_func"]
    retrieval_timestamp_prompt = PROMPTS['extract_timestamp_in_query']
    context_base = dict(
        tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
        record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
        completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
        timestamp_format=json.dumps(PROMPTS["DEFAULT_TIMESTAMP_FORMAT"]),
        timestamp_types=",".join(PROMPTS["DEFAULT_TEMPORAL_HIERARCHY"])
    )
    
    try:
        final_result = await use_llm_func(retrieval_timestamp_prompt.format(input_text=query, **context_base))
    except Exception as e:
        logger.info(f"An error occurred in timestamp extraction: {e}")
        final_result = ""
    
    if final_result is None:
        logger.warning("LLM function returned None for timestamp extraction, using empty string")
        final_result = ""
    
    if isinstance(final_result, tuple):
        final_result = final_result[0] if len(final_result) > 0 else ""
    elif isinstance(final_result, list):
        final_result = final_result[0].get("text", "") if len(final_result) > 0 and isinstance(final_result[0], dict) else ""

    if not isinstance(final_result, str):
        logger.warning(f"Unexpected final_result type: {type(final_result)}, converting to string")
        final_result = str(final_result) if final_result is not None else ""

    if not final_result.strip():
        logger.warning("No valid timestamp extraction result, returning empty results")
        return [], [], None

    records = split_string_by_multi_markers(
        final_result,
        [PROMPTS["DEFAULT_RECORD_DELIMITER"], PROMPTS["DEFAULT_COMPLETION_DELIMITER"]],
    )

    timestamp_candidates, temporal_granularity = [], None
    
    normalizer = get_temporal_normalizer()
    
    for record in records:
        record = re.search(r"\((.*)\)", record)
        if record is None:
            continue
        record = record.group(1)
        record_attributes = split_string_by_multi_markers(
            record, [PROMPTS["DEFAULT_TUPLE_DELIMITER"]]
        )
        
        if_timestamp = await _handle_single_timestamp_extraction(
            record_attributes,
        )
        if if_timestamp is not None:
            if normalizer:
                if isinstance(if_timestamp.get('timestamp'), str):
                    timestamp_value = if_timestamp['timestamp'].strip('"')
                    normalized_result = normalizer.normalize_temporal_expression(timestamp_value)
                    if normalized_result.normalized_forms:
                        if_timestamp['timestamp'] = normalized_result.normalized_forms[0]
                        if_timestamp['normalized_confidence'] = normalized_result.confidence
                        if_timestamp['normalized_forms'] = normalized_result.normalized_forms
                        logger.info(f"Enhanced normalized timestamp: {timestamp_value} -> {normalized_result.normalized_forms[0]} (confidence: {normalized_result.confidence}, type: {normalized_result.normalization_type})")
                elif isinstance(if_timestamp.get('timestamp'), list):
                    normalized_timestamps = []
                    for ts in if_timestamp['timestamp']:
                        ts_clean = ts.strip('"')
                        normalized_result = normalizer.normalize_temporal_expression(ts_clean)
                        if normalized_result.normalized_forms:
                            normalized_timestamps.append(normalized_result.normalized_forms[0])
                            logger.info(f"Enhanced normalized timestamp: {ts_clean} -> {normalized_result.normalized_forms[0]} (confidence: {normalized_result.confidence}, type: {normalized_result.normalization_type})")
                        else:
                            normalized_timestamps.append(ts)
                    if_timestamp['timestamp'] = normalized_timestamps
            
            timestamp_candidates.append(if_timestamp)
    
    type2num = PROMPTS["DEFAULT_TEMPORAL_HIERARCHY_LEVEL"]
    timestamps = []
    sub_timestamps = []
    
    for ts in timestamp_candidates:
        if ts is None:
            logger.warning("Skipping None timestamp candidate")
            continue
        try:
            if ts.get('temporal_logic') == 'before':
                temporal_granularity = ts.get('entity_type')
                if not temporal_granularity:
                    logger.warning("Missing entity_type in timestamp candidate")
                    continue
                sibling_nodes = [key for key, value in temporal_hierarchy.items() if
                                 value['level'] == type2num.get(temporal_granularity.lower(), 'UNKNOWN')]
                sibling_nodes_sorted = sort_timestamp_by_datetime(sibling_nodes)
                timestamp_value = ts.get('timestamp')
                if not timestamp_value:
                    logger.warning("Missing timestamp in timestamp candidate")
                    continue
                timestamps = [s_n for s_n in sibling_nodes_sorted if
                              convert_timestamp_to_datetime(s_n) < convert_timestamp_to_datetime(timestamp_value)]
                for timestamp in timestamps:
                    found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
                    if found:
                        sub_timestamps.extend(temporal_hierarchy[matched_key]['sub_communities'])
                    else:
                        logger.warning(f"Timestamp {timestamp} not found in temporal hierarchy")
                        
            elif ts.get('temporal_logic') == 'after':
                temporal_granularity = ts.get('entity_type')
                if not temporal_granularity:
                    logger.warning("Missing entity_type in timestamp candidate")
                    continue
                sibling_nodes = [key for key, value in temporal_hierarchy.items() if
                                 value['level'] == type2num.get(temporal_granularity.lower(), 'UNKNOWN')]
                sibling_nodes_sorted = sort_timestamp_by_datetime(sibling_nodes)

                timestamp_value = ts.get('timestamp')
                if not timestamp_value:
                    logger.warning("Missing timestamp in timestamp candidate")
                    continue
                timestamps = [s_n for s_n in sibling_nodes_sorted if
                              convert_timestamp_to_datetime(s_n) > convert_timestamp_to_datetime(timestamp_value)]
                for timestamp in timestamps:
                    found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
                    if found:
                        sub_timestamps.extend(temporal_hierarchy[matched_key]['sub_communities'])
                    else:
                        logger.warning(f"Timestamp {timestamp} not found in temporal hierarchy")
                        
            elif ts.get('temporal_logic') == 'at':
                temporal_granularity = ts.get('entity_type')
                if not temporal_granularity:
                    logger.warning("Missing entity_type in timestamp candidate")
                    continue
                timestamp_value = ts.get('timestamp')
                if not timestamp_value:
                    logger.warning("Missing timestamp in timestamp candidate")
                    continue
                found, matched_key = _find_timestamp_in_hierarchy(timestamp_value, temporal_hierarchy)
                if found:
                    sub_timestamps.extend(temporal_hierarchy[matched_key]['sub_communities'])
                    timestamps.append(matched_key)
                else:
                    logger.warning(f"Timestamp {timestamp_value} not found in temporal hierarchy")
                    
            elif ts.get('temporal_logic') == 'between':
                temporal_granularity = ts.get('entity_type')
                if not temporal_granularity:
                    logger.warning("Missing entity_type in timestamp candidate")
                    continue
                timestamp_value = ts.get('timestamp')
                if not timestamp_value or not isinstance(timestamp_value, list) or len(timestamp_value) < 2:
                    logger.warning("Missing or invalid timestamp list in timestamp candidate")
                    continue
                sibling_nodes = [key for key, value in temporal_hierarchy.items() if
                                 value['level'] == type2num.get(temporal_granularity.lower(), 'UNKNOWN')]
                sibling_nodes_sorted = sort_timestamp_by_datetime(sibling_nodes)
                timestamps = [s_n for s_n in sibling_nodes_sorted if
                              convert_timestamp_to_datetime(timestamp_value[0]) <= convert_timestamp_to_datetime(
                                  s_n) <= convert_timestamp_to_datetime(timestamp_value[1])]
                for timestamp in timestamps:
                    found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
                    if found:
                        sub_timestamps.extend(temporal_hierarchy[matched_key]['sub_communities'])
                    else:
                        logger.warning(f"Timestamp {timestamp} not found in temporal hierarchy")
                        
            else:
                temporal_granularity = ts.get('entity_type')
                if not temporal_granularity:
                    logger.warning("Missing entity_type in timestamp candidate")
                    continue
                timestamp_value = ts.get('timestamp')
                if not timestamp_value:
                    logger.warning("Missing timestamp in timestamp candidate")
                    continue
                
                found, matched_key = _find_timestamp_in_hierarchy(timestamp_value, temporal_hierarchy)
                if found:
                    sub_timestamps.extend(temporal_hierarchy[matched_key]['sub_communities'])
                    timestamps.append(matched_key)
                    logger.info(f"Found timestamp match: {timestamp_value} -> {matched_key}")
                else:
                    logger.warning(f"Timestamp {timestamp_value} not found in temporal hierarchy")
                        
        except Exception as e:
            logger.warning(f"Error processing timestamp candidate {ts}: {e}")
            continue

    return timestamps, sub_timestamps, temporal_granularity


# Helper function: extract temporal granularity
async def _extract_temporal_granularity(query: str,
                                        global_config: dict,
                                        query_param: QueryParam,
                                        ):
    temporal_granularity = None
    if query_param.temporal_granularity:
        temporal_granularity = query_param.temporal_granularity
    else:
        use_llm_func: callable = global_config["best_model_func"]
        temporal_hierarchy_prompt = PROMPTS['extract_temporal_hierarchy']
        context_base = dict(
            tuple_delimiter=PROMPTS["DEFAULT_TUPLE_DELIMITER"],
            record_delimiter=PROMPTS["DEFAULT_RECORD_DELIMITER"],
            completion_delimiter=PROMPTS["DEFAULT_COMPLETION_DELIMITER"],
            timestamp_format=json.dumps(PROMPTS["DEFAULT_TIMESTAMP_FORMAT"]),
            timestamp_types=",".join(PROMPTS["DEFAULT_TEMPORAL_HIERARCHY"])
        )
        try:
            llm_temporal_granularity = await use_llm_func(
                temporal_hierarchy_prompt.format(input_text=query, **context_base))
        except Exception as e:
            logger.info(f"An error occurred: {e}")
            llm_temporal_granularity = ("",)
        
        if llm_temporal_granularity is None:
            logger.warning("LLM function returned None for temporal granularity, using empty string")
            llm_temporal_granularity = ("",)
        
        llm_temporal_granularity = llm_temporal_granularity[0]
        if isinstance(llm_temporal_granularity, list):
            llm_temporal_granularity = llm_temporal_granularity[0]["text"]
        records = split_string_by_multi_markers(
            llm_temporal_granularity,
            [PROMPTS["DEFAULT_RECORD_DELIMITER"], PROMPTS["DEFAULT_COMPLETION_DELIMITER"]],
        )

        if not records:
            logger.warning("No records found in temporal granularity extraction")
            return temporal_granularity
            
        record = re.search(r"\((.*)\)", records[0])
        if record:
            record = record.group(1)
            record_attributes = split_string_by_multi_markers(
                record, [PROMPTS["DEFAULT_TUPLE_DELIMITER"]]
            )
            if len(record_attributes) >= 2:
                temporal_granularity = clean_str(record_attributes[1].lower())
                temporal_granularity = temporal_granularity.strip('"').upper() if isinstance(temporal_granularity, str) else temporal_granularity.value.upper()
    return temporal_granularity


# Helper function: timestamp alignment
async def _timestamp_alignment(
        timestamp_in_query: list[str],
        temporal_granularity: str,
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        preferred_temporal_granularity: None = None,
):
    from ..utils.helpers import get_parent_timestamp_name
    
    type2num = PROMPTS["DEFAULT_TEMPORAL_HIERARCHY_LEVEL"]
    aligned_timestamp_in_query = []
    
    logger.info(f"DEBUG: _timestamp_alignment called with:")
    logger.info(f"DEBUG:   timestamp_in_query: {timestamp_in_query}")
    logger.info(f"DEBUG:   temporal_granularity: {temporal_granularity}")
    logger.info(f"DEBUG:   preferred_temporal_granularity: {preferred_temporal_granularity}")
    logger.info(f"DEBUG:   temporal_hierarchy keys: {list(temporal_hierarchy.keys())}")
    logger.info(f"DEBUG:   type2num: {type2num}")
    
    if timestamp_in_query and preferred_temporal_granularity:
        logger.info(f"DEBUG: Case 1: Both timestamp_in_query and preferred_temporal_granularity exist")
        if preferred_temporal_granularity == temporal_granularity:
            logger.info(f"DEBUG:   Granularities match, using timestamp_in_query as-is")
            aligned_timestamp_in_query = timestamp_in_query
        elif type2num.get(preferred_temporal_granularity.lower(), 'UNKNOWN') > type2num.get(
                temporal_granularity.lower(), 'UNKNOWN'):
            logger.info(f"DEBUG:   Preferred granularity is higher level, breaking down timestamps")
            for timestamp in timestamp_in_query:
                found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
                if found:
                    timestamp_data = temporal_hierarchy[matched_key]
                    if 'sub_communities' in timestamp_data:
                        logger.info(f"DEBUG:     Adding sub_communities for {timestamp} -> {matched_key}: {timestamp_data['sub_communities']}")
                        aligned_timestamp_in_query.extend(timestamp_data['sub_communities'])
            aligned_timestamp_in_query.extend(timestamp_in_query)
        elif type2num.get(preferred_temporal_granularity.lower(), 'UNKNOWN') < type2num.get(
                temporal_granularity.lower(), 'UNKNOWN'):
            logger.info(f"DEBUG:   Preferred granularity is lower level, getting parent timestamps")
            aligned_timestamp_in_query = [get_parent_timestamp_name(timestamp, preferred_temporal_granularity) for
                                          timestamp in timestamp_in_query]
            aligned_timestamp_in_query.extend(timestamp_in_query)
    elif not timestamp_in_query and preferred_temporal_granularity:
        logger.info(f"DEBUG: Case 2: No timestamp_in_query but preferred_temporal_granularity exists")
        aligned_timestamp_in_query = [key for key, value in temporal_hierarchy.items() if
                                      value['level'] == preferred_temporal_granularity]
        logger.info(f"DEBUG:   Found timestamps with preferred granularity: {aligned_timestamp_in_query}")
    elif timestamp_in_query and not preferred_temporal_granularity:
        logger.info(f"DEBUG: Case 3: timestamp_in_query exists but no preferred_temporal_granularity")
        aligned_timestamp_in_query = timestamp_in_query
    else:
        logger.info(f"DEBUG: Case 4: Neither timestamp_in_query nor preferred_temporal_granularity exists")
    
    logger.info(f"DEBUG: Final aligned_timestamp_in_query: {aligned_timestamp_in_query}")
    return aligned_timestamp_in_query


# Helper function: get seed nodes from relations
async def _get_seed_nodes_from_relations(query: str, 
                                        relations_vdb: BaseVectorStorage, 
                                        top_k: int,
                                        knowledge_graph_inst: BaseGraphStorage) -> list[dict]:
    if relations_vdb is None:
        logger.warning("Relations vector database is not available")
        return []
    
    relation_results = await relations_vdb.query(query, top_k=top_k)
    
    logger.info(f"Retrieved {len(relation_results)} relations for seed node extraction:")
    for i, result in enumerate(relation_results):
        logger.info(f"  {i+1}. {result.get('entity_name', 'UNKNOWN')} (similarity: {result.get('similarity', 0):.3f})")
    
    entity_names = set()
    for result in relation_results:
        entity_name = result.get('entity_name', '')
        if entity_name:
            parts = entity_name.split('_')
            if len(parts) >= 2:
                src_id = parts[0]
                tgt_id = parts[1]
                entity_names.add(src_id)
                entity_names.add(tgt_id)
            elif '->' in entity_name:
                src_tgt = entity_name.split('->')
                if len(src_tgt) >= 2:
                    src_id = src_tgt[0].strip()
                    tgt_id = src_tgt[1].strip()
                    entity_names.add(src_id)
                    entity_names.add(tgt_id)
            elif len(entity_name) > 0 and not any(char in entity_name for char in ['_', '->', '-']):
                entity_names.add(entity_name)
    
    seed_nodes = []
    for entity_name in list(entity_names):
        node_data = await knowledge_graph_inst.get_node(entity_name)
        if node_data is not None:
            best_similarity = 0.0
            for result in relation_results:
                if entity_name in result.get('entity_name', ''):
                    best_similarity = max(best_similarity, result.get('similarity', 0.0))
            
            seed_nodes.append({
                'entity_name': entity_name,
                'similarity': best_similarity,
                **node_data
            })
    
    seed_nodes.sort(key=lambda x: x.get('similarity', 0.0), reverse=True)
    seed_nodes = seed_nodes[:top_k]
    
    logger.info(f"Extracted {len(seed_nodes)} seed nodes from relations:")
    for i, node in enumerate(seed_nodes):
        logger.info(f"  {i+1}. {node.get('entity_name', 'UNKNOWN')} (similarity: {node.get('similarity', 0):.3f})")
    
    return seed_nodes


# Helper function: get all descendant timestamps from a timestamp
def _get_all_descendant_timestamps(timestamp: str, temporal_hierarchy: dict[str, SingleTemporalSchema]) -> set[str]:
    result = {timestamp}
    found, matched_key = _find_timestamp_in_hierarchy(timestamp, temporal_hierarchy)
    if found:
        timestamp_data = temporal_hierarchy.get(matched_key, {})
        if 'sub_communities' in timestamp_data:
            for sub_ts in timestamp_data['sub_communities']:
                result.update(_get_all_descendant_timestamps(sub_ts, temporal_hierarchy))
    return result


# Helper function: retrieve chunks using paper's PPR-based algorithm
async def _retrieve_chunks_with_ppr_algorithm(
        query: str,
        relations_vdb: BaseVectorStorage,
        knowledge_graph_inst: BaseGraphStorage,
        aligned_timestamp_in_query: list[str],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        query_param: QueryParam,
        global_config: dict,
        temporal_hierarchy: dict[str, SingleTemporalSchema] = None,
        retrieval_detail: dict = None,  # <-- 1. THÊM PARAMETER CHO SIGNATURE
) -> list[TextChunkSchema]:
    """
    Retrieve chunks using the paper's local retrieval algorithm.
    """
    # <-- 2. KHỞI TẠO RETRIEVAL_DETAIL NẾU NONE
    if retrieval_detail is None:
        retrieval_detail = {}

    logger.info(f"========================================")
    logger.info(f"Starting PPR-based chunk retrieval")
    logger.info(f"Query: '{query}'")
    logger.info(f"========================================")
    if not relations_vdb:
        logger.warning("Relations vector database not available, falling back to entity-based retrieval")
        return []
    
    top_k_relations = query_param.top_k * 3
    logger.info(f"========== Step 1: Query Relations Vector DB ==========")
    logger.info(f"Query: '{query}'")
    logger.info(f"Top K relations to retrieve: {top_k_relations}")
    relations_query_result = await relations_vdb.query(query, top_k=top_k_relations)
    logger.info(f"Retrieved {len(relations_query_result)} relation edges")
    if relations_query_result:
        logger.info(f"Top 10 relation results:")
        for i, rel in enumerate(relations_query_result[:10]):
            logger.info(f"  {i+1}. {rel.get('entity_name', 'UNKNOWN')} (similarity: {rel.get('similarity', 0):.4f})")
    else:
        logger.warning(f"No relations found!")
    
    if not relations_query_result:
        logger.warning("No relations found for query, falling back to entity-based retrieval")
        return []
    
    logger.info(f"========== Step 2: Filter Relations by Timestamps ==========")
    logger.info(f"Query timestamps (aligned): {aligned_timestamp_in_query}")
    no_timestamp = not aligned_timestamp_in_query
    logger.info(f"No timestamp filtering: {no_timestamp}")
    seed_nodes = set()
    relation_metadata = {}

    timestamps_set = set()
    if not no_timestamp and temporal_hierarchy:
        logger.info(f"Expanding timestamps using temporal hierarchy...")
        for query_ts in aligned_timestamp_in_query:
            descendants = _get_all_descendant_timestamps(query_ts, temporal_hierarchy)
            logger.info(f"  '{query_ts}' -> {len(descendants)} descendants: {sorted(list(descendants))[:10]}...")
            timestamps_set.update(descendants)
        timestamps_set = {ts.replace('"', '').replace("'", '') for ts in timestamps_set}
        logger.info(f"Expanded from {len(aligned_timestamp_in_query)} to {len(timestamps_set)} total timestamps")
        logger.info(f"All expanded timestamps: {sorted(list(timestamps_set))}")
    elif not no_timestamp:
        timestamps_set = {ts.replace('"', '').replace("'", '') for ts in aligned_timestamp_in_query}
        logger.info(f"No temporal hierarchy available, using query timestamps as-is: {sorted(list(timestamps_set))}")
    
    logger.info(f"Processing {len(relations_query_result)} relations to extract seed nodes...")
    matched_count = 0
    skipped_count = 0
    for idx, relation in enumerate(relations_query_result):
        entity_name = relation.get('entity_name', '')
        similarity = relation.get('similarity', 0.0)
        
        names = entity_name.split('_')
        if len(names) >= 2:
            src_id = names[0]
            tgt_id = names[1]
            
            if no_timestamp:
                seed_nodes.add(src_id)
                seed_nodes.add(tgt_id)
                if idx < 5:
                    logger.info(f"  [{idx+1}] {entity_name} -> seed nodes: {src_id}, {tgt_id} (no timestamp filter)")
                matched_count += 1
            else:
                if len(names) == 3: 
                    timestamp = names[2]
                    timestamp_clean = timestamp.replace('"', '').replace("'", '')
                    if timestamp_clean in timestamps_set:
                        seed_nodes.add(src_id)
                        seed_nodes.add(tgt_id)
                        relation_metadata[(src_id, tgt_id, timestamp_clean)] = similarity
                        if matched_count < 5:
                            logger.info(f"  [{idx+1}] {entity_name} -> MATCHED (timestamp: {timestamp_clean}) -> seed nodes: {src_id}, {tgt_id}")
                        matched_count += 1
                    else:
                        if skipped_count < 5:
                            logger.info(f"  [{idx+1}] {entity_name} -> SKIPPED (timestamp: {timestamp_clean} not in timestamps_set)")
                        skipped_count += 1
                elif len(names) == 2:
                    if skipped_count < 5:
                        logger.info(f"  [{idx+1}] {entity_name} -> SKIPPED (no timestamp in relation name)")
                    skipped_count += 1
    
    logger.info(f"Filtering summary: {matched_count} relations matched, {skipped_count} skipped")
    
    if not seed_nodes:
        logger.warning(f"========== ERROR: No seed nodes found after timestamp filtering! ==========")
        relation_timestamps = set()
        for relation in relations_query_result:
            entity_name = relation.get('entity_name', '')
            names = entity_name.split('_')
            if len(names) >= 3:
                relation_timestamps.add(names[2])
        logger.warning(f"Query timestamps (expanded): {sorted(list(timestamps_set))}")
        logger.warning(f"Found relation timestamps in retrieved relations: {sorted(list(relation_timestamps))[:30]}")
        logger.warning(f"Total unique relation timestamps: {len(relation_timestamps)}")
        return []
    
    logger.info(f"========== Step 3: Seed Nodes Extracted ==========")
    logger.info(f"Found {len(seed_nodes)} unique seed nodes from {len(relations_query_result)} relations")
    logger.info(f"Sample seed nodes (first 20): {list(seed_nodes)[:20]}")
    logger.info(f"Relation metadata entries: {len(relation_metadata)}")
    
    logger.info(f"========== Step 4: Run PageRank ==========")
    logger.info(f"Personalization nodes (seed nodes): {len(seed_nodes)}")
    logger.info(f"Top K to retrieve: {query_param.top_k * 2}")
    logger.info(f"Alpha (damping factor): 0.85")
    ppr_results = await knowledge_graph_inst.get_top_pagerank_nodes(
        personalization_nodes=list(seed_nodes),
        top_k=query_param.top_k * 2,
        alpha=0.85
    )
    logger.info(f"PPR computed for {len(ppr_results)} nodes")
    if ppr_results:
        logger.info(f"Top 10 PPR results:")
        for i, (node_id, score) in enumerate(ppr_results[:10]):
            logger.info(f"  {i+1}. {node_id} (PPR score: {score:.6f})")
    
    # <-- 2. CẬP NHẬT DỮ LIỆU VÀO RETRIEVAL_DETAIL SAU PPR KHI CÓ KẾT QUẢ
    retrieval_detail["seed_nodes"] = list(seed_nodes)
    retrieval_detail["ppr_scores"] = dict(ppr_results)
    retrieval_detail["timestamps"] = aligned_timestamp_in_query
    # Convert tuple keys to string for cleaner/serializable dict storage if needed
    retrieval_detail["relation_metadata"] = {f"{k[0]}_{k[1]}_{k[2]}": v for k, v in relation_metadata.items()}

    ppr_scores = {node_id: score for node_id, score in ppr_results}
    
    chunk_edge_scores = defaultdict(float)
    chunk_edge_similarities = defaultdict(list)
    
    edges_processed = 0
    edges_with_data = 0
    chunks_scored = 0
    
    for i in range(len(ppr_results)):
        for j in range(i + 1, len(ppr_results)):
            edges_processed += 1
            src_id = ppr_results[i][0]
            tgt_id = ppr_results[j][0]
            
            edge_data = await knowledge_graph_inst.get_edge(src_id, tgt_id)
            if not edge_data:
                continue
            
            edges_with_data += 1
            edge_score = ppr_scores.get(src_id, 0.0) + ppr_scores.get(tgt_id, 0.0)
            source_id_dict = edge_data.get('source_id', {})
            
            if isinstance(source_id_dict, dict):
                edge_similarity = 0.0
                for (s, t, ts), sim in relation_metadata.items():
                    if s == src_id and t == tgt_id:
                        edge_similarity = sim
                        break
                
                if no_timestamp:
                    for timestamp, chunk_id in source_id_dict.items():
                        chunk_edge_scores[chunk_id] += edge_score
                        chunk_edge_similarities[chunk_id].append(edge_similarity)
                        chunks_scored += 1
                else:
                    for timestamp_clean in timestamps_set:
                        for ts_variant in [timestamp_clean, f'"{timestamp_clean}"', timestamp_clean.replace('"', '')]:
                            if ts_variant in source_id_dict:
                                chunk_id = source_id_dict[ts_variant]
                                chunk_edge_scores[chunk_id] += edge_score
                                chunk_edge_similarities[chunk_id].append(edge_similarity)
                                chunks_scored += 1
                                break
            elif isinstance(source_id_dict, str):
                chunk_ids = split_string_by_multi_markers(source_id_dict, [GRAPH_FIELD_SEP])
                
                edge_similarity = 0.0
                for (s, t, ts), sim in relation_metadata.items():
                    if s == src_id and t == tgt_id:
                        edge_similarity = sim
                        break
                
                for chunk_id in chunk_ids:
                    chunk_edge_scores[chunk_id] += edge_score
                    chunk_edge_similarities[chunk_id].append(edge_similarity)
                    chunks_scored += 1
    
    logger.info(f"Edge processing summary:")
    logger.info(f"  Total edge pairs checked: {edges_processed}")
    logger.info(f"  Edges with data found: {edges_with_data}")
    logger.info(f"  Unique chunks scored: {len(chunk_edge_scores)}")
    
    logger.info(f"========== Step 6: Calculate Final Chunk Scores ==========")
    doc_scores = {}
    for chunk_id, edge_score_sum in chunk_edge_scores.items():
        similarities = chunk_edge_similarities.get(chunk_id, [])
        chunk_weight = 1.0
        for gamma_epsilon in similarities:
            chunk_weight *= (1.0 + gamma_epsilon)
        
        doc_scores[chunk_id] = chunk_weight * edge_score_sum
    
    sorted_chunks = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    logger.info(f"Scored {len(sorted_chunks)} chunks total")
    if sorted_chunks:
        logger.info(f"Top 10 chunk scores:")
        for i, (chunk_id, score) in enumerate(sorted_chunks[:10]):
            logger.info(f"  {i+1}. {chunk_id} (score: {score:.6f})")
    else:
        logger.warning(f"No chunks scored! This means no edges were matched to chunks.")
    
    logger.info(f"========== Step 7: Retrieve Chunk Data ==========")
    logger.info(f"Selecting top {query_param.top_k} chunks by score")
    top_chunk_ids = [chunk_id for chunk_id, score in sorted_chunks[:query_param.top_k]]
    logger.info(f"Selected {len(top_chunk_ids)} chunk IDs to retrieve")
    
    chunks = []
    tiktoken_model_name = global_config.get("tiktoken_model_name", "gpt-4o-mini")
    from ..utils.helpers import encode_string_by_tiktoken
    
    total_tokens = 0
    max_tokens = query_param.local_max_token_for_text_unit
    logger.info(f"Token limit: {max_tokens}")
    
    for i, chunk_id in enumerate(top_chunk_ids):
        try:
            chunk_data = await text_chunks_db.get_by_id(chunk_id)
            if chunk_data is None:
                logger.warning(f"  [{i+1}] Chunk {chunk_id} not found in text_chunks_db")
                continue
            
            chunk_content = chunk_data.get("content", "")
            chunk_tokens = len(encode_string_by_tiktoken(chunk_content, model_name=tiktoken_model_name))
            
            if total_tokens + chunk_tokens > max_tokens:
                logger.info(f"Reached token limit ({total_tokens}/{max_tokens}), stopping chunk retrieval")
                break
            
            chunks.append(chunk_data)
            total_tokens += chunk_tokens
            logger.info(f"  [{i+1}] Retrieved chunk {chunk_id} ({chunk_tokens} tokens, total: {total_tokens}/{max_tokens})")
            
        except Exception as e:
            logger.warning(f"Error retrieving chunk {chunk_id}: {e}")
            continue
    
    logger.info(f"========== Final Result ==========")
    logger.info(f"Retrieved {len(chunks)} chunks with total {total_tokens} tokens (limit: {max_tokens})")
    return chunks


# Helper function: iterative evidence retrieval
async def _iterative_evidence_retrieval(
        query: str,
        entities_vdb: BaseVectorStorage,
        relations_vdb: BaseVectorStorage,
        knowledge_graph_inst: BaseGraphStorage,
        aligned_timestamp_in_query: list[str],
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        query_param: QueryParam,
        global_config: dict,
        community_reports: BaseKVStorage[TemporalSchema],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        retrieval_detail: dict = None,  # <-- CHUYỂN TIẾP BIẾN TỪ HÀM CHA
) -> dict:
    all_evidence = {
        'entities': [],
        'relations': [],
        'communities': [],
        'text_units': []
    }
    
    all_evidence['entities'] = []
    all_evidence['relations'] = []
    all_evidence['communities'] = []
    
    if query_param.local_max_token_for_text_unit:
        # <-- TRUYỀN BIẾN THÀNH CÔNG VÀO HÀM PPR THỰC THI
        use_text_units = await _retrieve_chunks_with_ppr_algorithm(
            query,
            relations_vdb,
            knowledge_graph_inst,
            aligned_timestamp_in_query,
            text_chunks_db,
            query_param,
            global_config,
            temporal_hierarchy,
            retrieval_detail=retrieval_detail
        )
        all_evidence['text_units'] = use_text_units
        logger.info(f"[LOCAL QUERY] Retrieved {len(use_text_units)} text units (original chunks) from PPR algorithm")
    else:
        logger.warning("[LOCAL QUERY] local_max_token_for_text_unit is 0 or None - no text units will be retrieved!")
    
    logger.info(f"[LOCAL QUERY] Evidence summary: {len(all_evidence['entities'])} entities, {len(all_evidence['relations'])} relations, {len(all_evidence['communities'])} communities, {len(all_evidence['text_units'])} text_units")
    return all_evidence


# Helper function: supplemental evidence retrieval
async def _supplemental_evidence_retrieval(
        query: str,
        entities_vdb: BaseVectorStorage,
        relations_vdb: BaseVectorStorage,
        knowledge_graph_inst: BaseGraphStorage,
        aligned_timestamp_in_query: list[str],
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        query_param: QueryParam,
        global_config: dict,
        existing_evidence: dict,
        community_reports: BaseKVStorage[TemporalSchema],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
) -> dict:
    additional_evidence = {
        'entities': [],
        'relations': [],
        'communities': [],
        'text_units': []
    }
    
    if query_param.seed_node_method == "entities":
        logger.info("Trying relations-based retrieval as supplement")
        try:
            relation_results = await _get_seed_nodes_from_relations(query, relations_vdb, query_param.top_k, knowledge_graph_inst)
            if relation_results:
                relation_node_datas = await asyncio.gather(
                    *[knowledge_graph_inst.get_node(r["entity_name"]) for r in relation_results]
                )
                node_degrees = await asyncio.gather(
                    *[knowledge_graph_inst.node_degree(r["entity_name"]) for r in relation_results]
                )
                relation_node_datas = []
                for k, n, d in zip(relation_results, relation_node_datas, node_degrees):
                    if n is not None:
                        rank = await calculate_temporal_aware_rank(
                            n, 
                            aligned_timestamp_in_query, 
                            temporal_hierarchy, 
                            d,
                            query
                        )
                        relation_node_datas.append({**n, "entity_name": k["entity_name"], "rank": rank})
                
                existing_entity_names = {e["entity_name"] for e in existing_evidence.get('entities', [])}
                new_entities = [e for e in relation_node_datas if e["entity_name"] not in existing_entity_names]
                additional_evidence['entities'].extend(new_entities)
        except Exception as e:
            logger.warning(f"Failed to get supplemental relation results: {e}")
    
    if aligned_timestamp_in_query and len(additional_evidence['entities']) < 2:
        logger.info("Trying broader temporal search as supplement")
        try:
            query_years = set()
            for ts in aligned_timestamp_in_query:
                if isinstance(ts, str):
                    if ts.isdigit() and len(ts) == 4:
                        query_years.add(ts)
                    elif '-' in ts:
                        year_part = ts.split('-')[0]
                        if year_part.isdigit() and len(year_part) == 4:
                            query_years.add(year_part)
            
            if query_years:
                broader_timestamps = []
                for ts in temporal_hierarchy.keys():
                    ts_clean = ts.strip('"')
                    if any(year in ts_clean for year in query_years):
                        broader_timestamps.append(ts)
                
                if broader_timestamps:
                    sub_graph_entities = await _get_entities_from_temporal_subgraph(broader_timestamps, temporal_hierarchy)
                    broader_results = await entities_vdb.temporal_query(query, sub_graph_entities=sub_graph_entities,
                                                                        top_k=query_param.top_k)
                    
                    if broader_results:
                        broader_node_datas = await asyncio.gather(
                            *[knowledge_graph_inst.get_node(r["entity_name"]) for r in broader_results]
                        )
                        broader_node_degrees = await asyncio.gather(
                            *[knowledge_graph_inst.node_degree(r["entity_name"]) for r in broader_results]
                        )
                        broader_node_datas = []
                        for k, n, d in zip(broader_results, broader_node_datas, broader_node_degrees):
                            if n is not None:
                                rank = await calculate_temporal_aware_rank(
                                    n, 
                                    aligned_timestamp_in_query, 
                                    temporal_hierarchy, 
                                    d,
                                    query
                                )
                                broader_node_datas.append({**n, "entity_name": k["entity_name"], "rank": rank})
                        
                        existing_entity_names = {e["entity_name"] for e in existing_evidence.get('entities', []) + additional_evidence['entities']}
                        new_broader_entities = [e for e in broader_node_datas if e["entity_name"] not in existing_entity_names]
                        additional_evidence['entities'].extend(new_broader_entities)
        except Exception as e:
            logger.warning(f"Failed to get broader temporal results: {e}")
    
    if len(additional_evidence['entities']) < 2:
        logger.info("Trying general search with higher top_k as supplement")
        try:
            general_results = await entities_vdb.query(query, top_k=query_param.top_k * 2)
            if general_results:
                general_node_datas = await asyncio.gather(
                    *[knowledge_graph_inst.get_node(r["entity_name"]) for r in general_results]
                )
                general_node_degrees = await asyncio.gather(
                    *[knowledge_graph_inst.node_degree(r["entity_name"]) for r in general_results]
                )
                general_node_datas = []
                for k, n, d in zip(general_results, general_node_datas, general_node_degrees):
                    if n is not None:
                        rank = await calculate_temporal_aware_rank(
                            n, 
                            aligned_timestamp_in_query, 
                            temporal_hierarchy, 
                            d,
                            query
                        )
                        general_node_datas.append({**n, "entity_name": k["entity_name"], "rank": rank})
                
                existing_entity_names = {e["entity_name"] for e in existing_evidence.get('entities', []) + additional_evidence['entities']}
                new_general_entities = [e for e in general_node_datas if e["entity_name"] not in existing_entity_names]
                additional_evidence['entities'].extend(new_general_entities)
        except Exception as e:
            logger.warning(f"Failed to get general search results: {e}")
    
    if additional_evidence['entities']:
        try:
            additional_relations = await _find_most_related_temporal_edges_from_entities(
                additional_evidence['entities'], query_param, knowledge_graph_inst, aligned_timestamp_in_query, query_param.top_k,
                temporal_hierarchy, query
            )
            additional_evidence['relations'] = additional_relations
        except Exception as e:
            logger.warning(f"Failed to get additional relations: {e}")
    
    try:
        additional_communities = await _find_most_related_temporal_community_from_entities(
            query_param, community_reports, aligned_timestamp_in_query
        )
        existing_community_ids = {c.get('id', '') for c in existing_evidence.get('communities', [])}
        new_communities = [c for c in additional_communities if c.get('id', '') not in existing_community_ids]
        additional_evidence['communities'] = new_communities
    except Exception as e:
        logger.warning(f"Failed to get additional communities: {e}")
    
    if query_param.local_max_token_for_text_unit and additional_evidence['entities']:
        try:
            if aligned_timestamp_in_query:
                additional_text_units = await _find_most_related_temporal_text_unit_from_entities(
                    additional_evidence['entities'], query_param, text_chunks_db, knowledge_graph_inst, aligned_timestamp_in_query
                )
            else:
                additional_text_units = await _find_most_related_text_unit_from_entities(
                    additional_evidence['entities'], query_param, text_chunks_db, knowledge_graph_inst,
                )
            additional_evidence['text_units'] = additional_text_units
        except Exception as e:
            logger.warning(f"Failed to get additional text units: {e}")
    
    logger.info(f"Supplemental retrieval added: {len(additional_evidence['entities'])} entities, {len(additional_evidence['relations'])} relations, {len(additional_evidence['communities'])} communities, {len(additional_evidence['text_units'])} text units")
    
    return additional_evidence


# Helper function: build local query context
async def _build_local_query_context(
        query,
        knowledge_graph_inst: BaseGraphStorage,
        entities_vdb: BaseVectorStorage,
        relations_vdb: BaseVectorStorage,
        community_reports: BaseKVStorage[TemporalSchema],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        query_param: QueryParam,
        global_config: dict,
        full_docs_db=None,
        retrieval_detail: dict = None,  # <-- CHUYỂN TIẾP TỪ LOCAL_QUERY VÀO ĐÂY
):
    timestamp_in_query, sub_timestamps, temporal_granularity = await _retrieve_timestamp(query, temporal_hierarchy,
                                                                                         global_config)
    
    preferred_temporal_granularity = await _extract_temporal_granularity(query, global_config, query_param)
    
    aligned_timestamp_in_query = await _timestamp_alignment(timestamp_in_query, temporal_granularity,
                                                            temporal_hierarchy, preferred_temporal_granularity)

    if aligned_timestamp_in_query:
        logger.info(
            f"Identified query timestamps, {', '.join(aligned_timestamp_in_query)}"
        )
    else:
        logger.info(
            f"No timestamps identified - using enhanced fallback retrieval"
        )
        if timestamp_in_query and temporal_granularity:
            available_timestamps = list(temporal_hierarchy.keys())
            if available_timestamps:
                available_years = set()
                for ts in available_timestamps:
                    ts_clean = ts.strip('"')
                    if ts_clean.isdigit() and len(ts_clean) == 4:
                        available_years.add(ts_clean)
                    elif '-' in ts_clean:
                        year_part = ts_clean.split('-')[0]
                        if year_part.isdigit() and len(year_part) == 4:
                            available_years.add(year_part)
                
                if available_years:
                    min_year = min(available_years)
                    max_year = max(available_years)
                    logger.warning(f"Query asks about timestamps that don't exist in the data. Available data covers years {min_year}-{max_year}, but query asks about different timeframe. Using enhanced fallback retrieval.")
                    logger.info("Using conservative temporal matching - no closest match fallback")
    
    # Enhanced iterative evidence retrieval
    all_evidence = await _iterative_evidence_retrieval(
        query, entities_vdb, relations_vdb, knowledge_graph_inst, 
        aligned_timestamp_in_query, temporal_hierarchy, query_param, global_config,
        community_reports, text_chunks_db, retrieval_detail=retrieval_detail  # <-- TRUYỀN VÀO ĐÂY
    )
    
    node_datas = all_evidence.get('entities', [])
    use_relations = all_evidence.get('relations', [])
    use_communities = all_evidence.get('communities', [])
    use_text_units = all_evidence.get('text_units', [])
    
    min_evidence_required = 4
    current_evidence_count = len(node_datas) + len(use_relations) + len(use_communities) + len(use_text_units)
    
    if current_evidence_count < min_evidence_required:
        logger.warning(f"Insufficient evidence retrieved ({current_evidence_count} < {min_evidence_required}). Attempting additional retrieval...")
        
        additional_evidence = await _supplemental_evidence_retrieval(
            query, entities_vdb, relations_vdb, knowledge_graph_inst,
            aligned_timestamp_in_query, temporal_hierarchy, query_param, global_config,
            existing_evidence=all_evidence, community_reports=community_reports, text_chunks_db=text_chunks_db
        )
        
        node_datas.extend(additional_evidence.get('entities', []))
        use_relations.extend(additional_evidence.get('relations', []))
        use_communities.extend(additional_evidence.get('communities', []))
        use_text_units.extend(additional_evidence.get('text_units', []))
        
        logger.info(f"After supplemental retrieval: {len(node_datas)} entities, {len(use_relations)} relations, {len(use_communities)} communities, {len(use_text_units)} text units")

    node_datas_time = [n for n in node_datas if n["entity_type"].lower() in PROMPTS['DEFAULT_TEMPORAL_HIERARCHY']]
    node_datas = [n for n in node_datas if n["entity_type"].lower() not in PROMPTS['DEFAULT_TEMPORAL_HIERARCHY']]

    node_datas = truncate_list_by_token_size(
        node_datas,
        key=lambda x: x.get("description", "UNKNOWN"),
        max_token_size=int(query_param.local_max_token_for_local_context * 0.2),
    )

    logger.info(f"Before truncation: {len(use_relations)} relations retrieved")
    
    use_relations = truncate_list_by_token_size(
        use_relations,
        key=lambda x: x.get("description", "UNKNOWN"),
        max_token_size=int(query_param.local_max_token_for_local_context * 0.8),
    )
    
    logger.info(f"After truncation: {len(use_relations)} relations kept (token limit: {int(query_param.local_max_token_for_local_context * 0.8)})")

    logger.info(
        f"For query: {query}, Using {len(node_datas)} entities, {len(use_communities)} communities, {len(use_relations)} relations, {len(use_text_units)} text units"
    )
    
    # <-- CẬP NHẬT THÊM CÁC THÔNG TIN RETRIEVAL DETAILS SẴN CÓ VÀO DICT
    if retrieval_detail is not None:
        retrieval_detail.update({
            "entity": len(node_datas),
            "relation": len(use_relations),
            "community": len(use_communities),
            "text_units": len(use_text_units),
            "total_evidence": len(node_datas) + len(use_relations) + len(use_communities) + len(use_text_units)
        })
    
    retrieval_details_summary = {
        "entity": len(node_datas),
        "relation": len(use_relations),
        "community": len(use_communities),
        "text_units": len(use_text_units),
        "total_evidence": len(node_datas) + len(use_relations) + len(use_communities) + len(use_text_units)
    }
    
    logger.info("Building context for LOCAL query ")
    logger.info("Only using text units (original chunks), not entities/relations/communities")
    
    if full_docs_db is None:
        full_docs_db = global_config.get("full_docs")
        if full_docs_db is None and hasattr(global_config, "full_docs"):
            full_docs_db = global_config.full_docs
    if full_docs_db is None:
        logger.warning("[BUILD CONTEXT] full_docs not available in global_config, will use fallback document IDs")
    
    processed_chunks = []
    chunk_formatter = """---NEW CHUNK---
Document Title: {full_doc_title}
Chunk Order Index: {chunk_order_index}
Chunk Content:
{chunk_content}
---END OF CHUNK---

"""
    
    for i, chunk in enumerate(use_text_units):
        chunk_content = chunk.get("content", "")
        chunk_order_index = chunk.get("chunk_order_index", i)
        full_doc_id = chunk.get("full_doc_id", "")
        
        full_doc_title = "Unknown Document"
        if full_docs_db and full_doc_id:
            try:
                doc_data = await full_docs_db.get_by_id(full_doc_id)
                if doc_data:
                    full_doc_title = doc_data.get("title", full_doc_id)
            except Exception as e:
                logger.debug(f"Could not retrieve title for doc {full_doc_id}: {e}")
                full_doc_title = full_doc_id
        
        formatted_chunk = chunk_formatter.format(
            chunk_content=chunk_content,
            chunk_order_index=chunk_order_index,
            full_doc_title=full_doc_title
        )
        processed_chunks.append(formatted_chunk)
    
    context = "".join(processed_chunks)
    
    logger.info(f"[BUILD CONTEXT] Final context built: {len(use_text_units)} text chunks formatted")
    logger.info(f"[BUILD CONTEXT] Skipped {len(node_datas)} entities, {len(use_relations)} relations, {len(use_communities)} communities")
    return context, retrieval_details_summary


# Helper function: map global communities
async def _map_global_communities(
        query: str,
        communities_data: list[TemporalSchema],
        query_param: QueryParam,
        global_config: dict,
):
    use_string_json_convert_func = global_config["convert_response_to_json_func"]
    use_model_func = global_config["best_model_func"]
    community_groups = []
    while len(communities_data):
        this_group = truncate_list_by_token_size(
            communities_data,
            key=lambda x: x["report_string"],
            max_token_size=query_param.global_max_token_for_community_report,
        )
        community_groups.append(this_group)
        communities_data = communities_data[len(this_group):]

    async def _process(community_truncated_datas: list[TemporalSchema]) -> dict:
        communities_section_list = [["id", "content", "rating", "importance"]]
        for i, c in enumerate(community_truncated_datas):
            communities_section_list.append(
                [
                    i,
                    c["report_string"],
                    c["report_json"].get("rating", 0),
                    len(c["temporal_edges"]) + len(c['nodes']),
                ]
            )
        community_context = list_of_list_to_csv(communities_section_list)
        sys_prompt_temp = PROMPTS["global_map_rag_points"]
        sys_prompt = sys_prompt_temp.format(context_data=community_context)
        response = await use_model_func(
            query,
            system_prompt=sys_prompt,
            **query_param.global_special_community_map_llm_kwargs,
        )
        data = use_string_json_convert_func(response)
        return data.get("points", [])

    logger.info(f"Grouping to {len(community_groups)} groups for global search")
    responses = await asyncio.gather(*[_process(c) for c in community_groups])
    return responses


# Main function: local query
async def local_query(
        query,
        knowledge_graph_inst: BaseGraphStorage,
        entities_vdb: BaseVectorStorage,
        relations_vdb: BaseVectorStorage,
        community_reports: BaseKVStorage[TemporalSchema],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        query_param: QueryParam,
        global_config: dict,
) -> str:
    try:
        use_model_func = global_config["best_model_func"]
        full_docs_db = global_config.get("full_docs")
        
        # <-- 3. KHỞI TẠO RETRIEVAL_DETAIL TRƯỚC KHI TRUYỀN VÀO CONTEXT BUILDER
        retrieval_details = {}  
        
        context, retrieval_details_summary = await _build_local_query_context(
            query,
            knowledge_graph_inst,
            entities_vdb,
            relations_vdb,
            community_reports,
            text_chunks_db,
            temporal_hierarchy,
            query_param,
            global_config,
            full_docs_db=full_docs_db,
            retrieval_detail=retrieval_details,  # <-- TRUYỀN VÀO CONTEXT BUILDER
        )
        
        # Đồng bộ hóa summary counts vào đối tượng chi tiết lớn để return đồng nhất dữ liệu
        retrieval_details.update(retrieval_details_summary)

        if query_param.only_need_context:
            return context, retrieval_details
        if context is None:
            return PROMPTS["fail_response"], {"entity": 0, "relation": 0, "community": 0}
        sys_prompt_temp = PROMPTS["local_rag_response"]
        sys_prompt = sys_prompt_temp.format(
            context_data=context, response_type=query_param.response_type
        )
        logger.info(f"query: \n{query}")
        logger.info(f"prompt: \n{sys_prompt}")
        response = await use_model_func(
            query,
            system_prompt=sys_prompt,
        )
        logger.info(f"response: \n{response}")
        return response, retrieval_details
    except Exception as e:
        logger.error(f"Error in local_query for query '{query}': {str(e)}")
        return PROMPTS["fail_response"], {"entity": 0, "relation": 0, "community": 0}


# Main function: global query
async def global_query(
        query,
        knowledge_graph_inst: BaseGraphStorage,
        entities_vdb: BaseVectorStorage,
        relations_vdb: BaseVectorStorage,
        community_reports: BaseKVStorage[TemporalSchema],
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        temporal_hierarchy: dict[str, SingleTemporalSchema],
        query_param: QueryParam,
        global_config: dict,
) -> str:
    community_schema = temporal_hierarchy
    community_schema = {
        k: v for k, v in community_schema.items() if v["level"] <= query_param.level
    }
    if not len(community_schema):
        return PROMPTS["fail_response"]
    use_model_func = global_config["best_model_func"]

    sorted_community_schemas = sorted(
        community_schema.items(),
        key=lambda x: (x[1]["level"], -len(x[1]['temporal_edges']), -len(x[1]['nodes'])),
        reverse=False,
    )
    sorted_community_schemas = sorted_community_schemas[
                               : query_param.global_max_consider_community
                               ]
    community_datas = await community_reports.get_by_ids(
        [k[0] for k in sorted_community_schemas]
    )
    community_datas = [c for c in community_datas if c is not None]
    community_datas = [
        c
        for c in community_datas
        if c["report_json"].get("rating", 0) >= query_param.global_min_community_rating
    ]
    community_datas = sorted(
        community_datas,
        key=lambda x: (len(x["temporal_edges"]), len(x['nodes']), x["report_json"].get("rating", 0)),
        reverse=True,
    )
    logger.info(f"Revtrieved {len(community_datas)} communities")

    map_communities_points = await _map_global_communities(
        query, community_datas, query_param, global_config
    )
    final_support_points = []
    for i, mc in enumerate(map_communities_points):
        for point in mc:
            if "description" not in point:
                continue
            final_support_points.append(
                {
                    "analyst": i,
                    "answer": point["description"],
                    "score": point.get("score", 1),
                }
            )
    final_support_points = [p for p in final_support_points if p["score"] > 0]
    if not len(final_support_points):
        return PROMPTS["fail_response"]
    final_support_points = sorted(
        final_support_points, key=lambda x: x["score"], reverse=True
    )
    final_support_points = truncate_list_by_token_size(
        final_support_points,
        key=lambda x: x["answer"],
        max_token_size=query_param.global_max_token_for_community_report,
    )
    points_context = []
    for dp in final_support_points:
        points_context.append(
            f"""----Analyst {dp['analyst']}----
Importance Score: {dp['score']}
{dp['answer']}
"""
        )
    points_context = "\n".join(points_context)
    if query_param.only_need_context:
        return points_context
    sys_prompt_temp = PROMPTS["global_reduce_rag_response"]
    response = await use_model_func(
        query,
        sys_prompt_temp.format(
            report_data=points_context, response_type=query_param.response_type
        ),
    )
    return response


# Main function: naive query
async def naive_query(
        query,
        chunks_vdb: BaseVectorStorage,
        text_chunks_db: BaseKVStorage[TextChunkSchema],
        query_param: QueryParam,
        global_config: dict,
):
    use_model_func = global_config["best_model_func"]
    results = await chunks_vdb.query(query, top_k=query_param.top_k)
    if not len(results):
        return PROMPTS["fail_response"]
    chunks_ids = [r["id"] for r in results]
    chunks = await text_chunks_db.get_by_ids(chunks_ids)

    maybe_trun_chunks = truncate_list_by_token_size(
        chunks,
        key=lambda x: x["content"],
        max_token_size=query_param.naive_max_token_for_text_unit,
    )
    logger.info(f"Truncate {len(chunks)} to {len(maybe_trun_chunks)} chunks")
    section = "--New Chunk--\n".join([c["content"] for c in maybe_trun_chunks])
    if query_param.only_need_context:
        return section
    sys_prompt_temp = PROMPTS["naive_rag_response"]
    sys_prompt = sys_prompt_temp.format(
        content_data=section, response_type=query_param.response_type
    )
    response = await use_model_func(
        query,
        system_prompt=sys_prompt,
    )
    return response


# Export aliases for backward compatibility
get_entities_from_temporal_subgraph = _get_entities_from_temporal_subgraph
get_broader_temporal_entities = _get_broader_temporal_entities
find_most_related_community_from_entities = _find_most_related_community_from_entities
find_most_related_text_unit_from_entities = _find_most_related_text_unit_from_entities
find_most_related_temporal_text_unit_from_entities = _find_most_related_temporal_text_unit_from_entities
find_most_related_edges_from_entities = _find_most_related_edges_from_entities
find_most_related_temporal_edges_from_entities = _find_most_related_temporal_edges_from_entities
find_most_related_temporal_edges_from_entities_topk_merged = _find_most_related_temporal_edges_from_entities_topk_merged
find_most_related_temporal_community_from_entities = _find_most_related_temporal_community_from_entities
retrieve_timestamp = _retrieve_timestamp
extract_temporal_granularity = _extract_temporal_granularity
timestamp_alignment = _timestamp_alignment
get_seed_nodes_from_relations = _get_seed_nodes_from_relations
build_local_query_context = _build_local_query_context
map_global_communities = _map_global_communities
iterative_evidence_retrieval = _iterative_evidence_retrieval
supplemental_evidence_retrieval = _supplemental_evidence_retrieval

__all__ = [
    "local_query",
    "global_query",
    "naive_query",
    "build_local_query_context",
    "map_global_communities",
    "retrieve_timestamp",
    "extract_temporal_granularity",
    "timestamp_alignment",
    "get_entities_from_temporal_subgraph",
    "get_seed_nodes_from_relations",
    "find_most_related_community_from_entities",
    "find_most_related_text_unit_from_entities",
    "find_most_related_temporal_text_unit_from_entities",
    "find_most_related_edges_from_entities",
    "find_most_related_temporal_edges_from_entities",
    "find_most_related_temporal_edges_from_entities_topk_merged",
    "find_most_related_temporal_community_from_entities",
    "iterative_evidence_retrieval",
    "supplemental_evidence_retrieval",
    "get_broader_temporal_entities",
    "calculate_temporal_aware_rank",
    "calculate_temporal_aware_edge_rank",
    "merge_edges_round_robin",
    "create_ranking_config",
    "GRAPH_FIELD_SEP",
    "PROMPTS",
]