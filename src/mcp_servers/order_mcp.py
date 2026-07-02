#!/usr/bin/env python3
"""
订单MCP服务
src/mcp_servers/order_mcp.py

提供订单创建、查询、管理的MCP服务
"""

import json
import uuid
from datetime import datetime
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.mcp_servers.base_service import DatabaseService
from src.config import config, logger


# 创建MCP服务实例
mcp = FastMCP("OrderMCP")


class OrderService(DatabaseService):
    """订单服务"""

    def generate_order_no(self) -> str:
        """生成订单号"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_suffix = str(uuid.uuid4().hex)[:6].upper()
        return f"ORD{timestamp}{random_suffix}"

    def get_ticket_info(self, ticket_type: str, ticket_id: int) -> Optional[dict]:
        """
        获取票务信息

        Args:
            ticket_type: 票务类型 (train/flight/concert)
            ticket_id: 票务ID

        Returns:
            票务信息字典
        """
        table_map = {
            "train": "train_tickets",
            "flight": "flight_tickets",
            "concert": "concert_tickets"
        }

        table = table_map.get(ticket_type)
        if not table:
            return None

        # 表名来自白名单映射，参数走占位符
        sql = f"SELECT * FROM {table} WHERE id = %s"
        result = self.execute_query(sql, (int(ticket_id),))

        try:
            data = json.loads(result)
            if data.get("status") == "success" and data.get("data"):
                return data["data"][0]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

        return None

    def update_remaining_seats(self, ticket_type: str, ticket_id: int, quantity: int) -> bool:
        """
        更新余票数量

        Args:
            ticket_type: 票务类型
            ticket_id: 票务ID
            quantity: 扣减数量

        Returns:
            是否更新成功
        """
        table_map = {
            "train": "train_tickets",
            "flight": "flight_tickets",
            "concert": "concert_tickets"
        }

        table = table_map.get(ticket_type)
        if not table:
            return False

        # 表名来自白名单映射，参数走占位符
        sql = f"""
        UPDATE {table}
        SET remaining_seats = remaining_seats - %s
        WHERE id = %s AND remaining_seats >= %s
        """

        result = self.execute_update(sql, (int(quantity), int(ticket_id), int(quantity)))
        return result.get("affected_rows", 0) > 0

    def create_order(
        self,
        ticket_type: str,
        ticket_id: int,
        quantity: int,
        contact_name: str,
        contact_phone: str,
        contact_id_card: str = ""
    ) -> dict:
        """
        创建订单

        Args:
            ticket_type: 票务类型
            ticket_id: 票务ID
            quantity: 数量
            contact_name: 联系人姓名
            contact_phone: 联系人电话
            contact_id_card: 身份证号

        Returns:
            订单创建结果
        """
        # 1. 获取票务信息
        ticket = self.get_ticket_info(ticket_type, ticket_id)
        if not ticket:
            return {"status": "error", "message": "票务不存在"}

        # 2. 检查余票
        remaining = ticket.get("remaining_seats", 0)
        if remaining < quantity:
            return {"status": "error", "message": f"余票不足，当前仅剩 {remaining} 张"}

        # 3. 计算价格
        unit_price = float(ticket.get("price", 0))
        total_price = unit_price * quantity

        # 4. 生成订单号
        order_no = self.generate_order_no()

        # 5. 扣减库存
        if not self.update_remaining_seats(ticket_type, ticket_id, quantity):
            return {"status": "error", "message": "库存扣减失败，请重试"}

        # 6. 创建订单
        sql = """
        INSERT INTO orders (
            order_no, ticket_type, ticket_id, quantity,
            unit_price, total_price, contact_name, contact_phone,
            contact_id_card, status
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            order_no, ticket_type, ticket_id, quantity,
            unit_price, total_price, contact_name, contact_phone,
            contact_id_card, "pending"
        )

        result = self.execute_insert(sql, params)

        if result.get("status") == "success":
            logger.info(f"订单创建成功: {order_no}")
            return {
                "status": "success",
                "data": {
                    "order_no": order_no,
                    "ticket_type": ticket_type,
                    "ticket_id": ticket_id,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "total_price": total_price,
                    "contact_name": contact_name,
                    "contact_phone": contact_phone,
                    "status": "pending"
                }
            }
        else:
            # 回滚库存
            self.update_remaining_seats(ticket_type, ticket_id, -quantity)
            return {"status": "error", "message": "订单创建失败"}

    def query_order(self, order_no: str) -> str:
        """查询订单"""
        return self.execute_query(
            "SELECT * FROM orders WHERE order_no = %s", (order_no,)
        )

    def cancel_order(self, order_no: str) -> dict:
        """取消订单"""
        # 1. 查询订单
        result = self.execute_query(
            "SELECT * FROM orders WHERE order_no = %s", (order_no,)
        )

        try:
            data = json.loads(result)
            if data.get("status") != "success" or not data.get("data"):
                return {"status": "error", "message": "订单不存在"}

            order = data["data"][0]
            if order.get("status") != "pending":
                return {"status": "error", "message": "只能取消待支付的订单"}

            # 2. 更新订单状态
            self.execute_update(
                "UPDATE orders SET status = 'cancelled' WHERE order_no = %s",
                (order_no,)
            )

            # 3. 恢复库存
            self.update_remaining_seats(
                order["ticket_type"],
                order["ticket_id"],
                -order["quantity"]
            )

            return {"status": "success", "message": "订单已取消"}

        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            return {"status": "error", "message": str(e)}


# 创建服务实例
order_service = OrderService()


@mcp.tool()
def create_order(
    ticket_type: str,
    ticket_id: int,
    quantity: int,
    contact_name: str,
    contact_phone: str,
    contact_id_card: str = ""
) -> str:
    """
    创建订单

    Args:
        ticket_type: 票务类型 (train/flight/concert)
        ticket_id: 票务ID
        quantity: 购买数量
        contact_name: 联系人姓名
        contact_phone: 联系人电话
        contact_id_card: 身份证号 (可选)

    Returns:
        JSON格式的订单创建结果
    """
    result = order_service.create_order(
        ticket_type=ticket_type,
        ticket_id=ticket_id,
        quantity=quantity,
        contact_name=contact_name,
        contact_phone=contact_phone,
        contact_id_card=contact_id_card
    )
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def query_order(order_no: str) -> str:
    """
    查询订单

    Args:
        order_no: 订单号

    Returns:
        JSON格式的订单信息
    """
    return order_service.query_order(order_no)


@mcp.tool()
def cancel_order(order_no: str) -> str:
    """
    取消订单

    Args:
        order_no: 订单号

    Returns:
        JSON格式的取消结果
    """
    result = order_service.cancel_order(order_no)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
def list_orders(
    contact_phone: str = None,
    status: str = None,
    limit: int = 10
) -> str:
    """
    查询订单列表

    Args:
        contact_phone: 联系人电话 (可选)
        status: 订单状态 (可选: pending/paid/cancelled/completed)
        limit: 返回数量限制

    Returns:
        JSON格式的订单列表
    """
    # 参数化查询，杜绝拼接注入
    conditions = ["1=1"]
    params = []
    if contact_phone:
        conditions.append("contact_phone = %s")
        params.append(contact_phone)
    if status:
        conditions.append("status = %s")
        params.append(status)
    params.append(min(int(limit), 50))

    sql = f"""
    SELECT order_no, ticket_type, quantity, total_price,
           contact_name, contact_phone, status, created_at
    FROM orders
    WHERE {' AND '.join(conditions)}
    ORDER BY created_at DESC
    LIMIT %s
    """

    return order_service.execute_query(sql, tuple(params))


def main():
    """启动订单MCP服务"""
    import uvicorn

    print("=" * 60)
    print("📋 订单 MCP 服务")
    print("=" * 60)
    print(f"服务地址: http://localhost:{config.mcp.order_port}")
    print(f"数据库:   {config.database.describe}")
    if config.mock_data:
        print("数据来源: 本地 mock 数据（随机生成），未接入真实票务 API")
    print("=" * 60)
    print("\n可用工具：")
    print("  - create_order: 创建订单")
    print("  - query_order: 查询订单")
    print("  - cancel_order: 取消订单")
    print("  - list_orders: 订单列表")
    print("=" * 60)

    uvicorn.run(
        mcp.streamable_http_app(),
        host="0.0.0.0",
        port=config.mcp.order_port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
