import rclpy 
from rclpy.node import Node

class DectorNode(Node):
    def __init(self):
        # name of the node
        super().__init__("dector_node")
        self.get_logger().info("DectorNode has been started.")


    def main(args=None):
        # 1. ROS2 communication initialization
        rclpy.init(args=args)
        # 2. Create the node
        node = DectorNode()
        # 3. Keep the node running until interrupted (start loop)
        rclpy.spin(node)
        # 4. Shutdown the node and cleanup
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()             

